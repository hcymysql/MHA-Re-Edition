#!/usr/bin/env python3

import pymysql
import os, sys, re, logging, configparser


class Config_Parser(object):
    @staticmethod
    def read_default(filename='app1.cnf'):
        parser_obj = configparser.RawConfigParser()
        parser_obj.read(filename, encoding='utf-8')
        server_default_dict = parser_obj.defaults()
        if len(server_default_dict) == 0:
            print('你的cnf配置文件设置不正确，请按照模板规范设置！')
            sys.exit('MySQL Replication Health is NOT OK!')
        return server_default_dict

    @staticmethod
    def read_server(filename='app1.cnf'):
        parser_obj = configparser.RawConfigParser()
        parser_obj.read(filename, encoding='utf-8')
        sections_count = int(len(parser_obj.sections()))
        if sections_count == 1:
            print('你的cnf配置文件只设置了一个MySQL，至少两个MySQL做一个主从复制，才满足最基本的高可用故障切换架构！')
            sys.exit('MySQL Replication Health is NOT OK!')
        elif not parser_obj.has_section('server1') and not parser_obj.has_section('server2'):
            print('你的cnf配置文件设置不正确，请按照模板规范设置！')
            sys.exit('MySQL Replication Health is NOT OK!')
        else:
            hosts_info_list = []
            for hosts_info in parser_obj.sections():
                _ip = str(parser_obj.get(hosts_info, 'ip'))
                _port = int(parser_obj.get(hosts_info, 'port'))
                _user = str(parser_obj.get(hosts_info, 'user'))
                _password = str(parser_obj.get(hosts_info, 'password'))
                _port = int(parser_obj.get(hosts_info, 'port'))
                _ssh_user = str(parser_obj.get(hosts_info, 'ssh_user'))
                _ssh_password = str(parser_obj.get(hosts_info, 'ssh_password'))
                _ssh_port = int(parser_obj.get(hosts_info, 'ssh_port'))
                try:
                    if parser_obj.get(hosts_info, 'candidate_master'):
                        _candidate_master = int(parser_obj.get(hosts_info, 'candidate_master'))
                        hosts_info_list.append([_ip, _port, _user, _password, _ssh_user, _ssh_password, _ssh_port, _candidate_master])
                except Exception as e:
                    #print(e)
                    hosts_info_list.append([_ip, _port, _user, _password, _ssh_user, _ssh_password, _ssh_port])
        return hosts_info_list


###### End class Config_Parser
#############################################################################################
class MySQL_Check(object):
    """
    这个类的作用是类似MHA的masterha_check_repl --conf=/etc/mha/app1.cnf
    先进行环境的基本检查，然后开启Automated Failover and Monitoring
    """

    def __init__(self, host, port, user, password):
        self._host = host
        self._port = int(port)
        self._user = user
        self._password = password
        self._connection = None
        try:
            self._connection = pymysql.connect(host=self._host, port=self._port, user=self._user, passwd=self._password)
        except pymysql.Error as e:
            print("Error %d: %s" % (e.args[0], e.args[1]))
            sys.exit('MySQL Replication Health is NOT OK!')

    def chek_repl_status(self):
        cursor = self._connection.cursor()
        master_info = slave_info = multi_tier_slave_info = []
        try:
            if cursor.execute('SHOW SLAVE HOSTS') >= 1 and cursor.execute('SHOW SLAVE STATUS') == 0:
                logging.info('%s:%s - 这是一台主库.' % (self._host, self._port))
                master_info = [self._host, self._port, self._user, self._password]
            elif cursor.execute('SHOW SLAVE HOSTS') == 0 and cursor.execute('SHOW SLAVE STATUS') == 1:
                logging.info('%s:%s - 这是一台从库.' % (self._host, self._port))
                slave_info = [self._host, self._port, self._user, self._password]
            elif cursor.execute('SHOW SLAVE HOSTS') >= 1 and cursor.execute('SHOW SLAVE STATUS') == 1:
                logging.info('%s:%s - 这是一台级联复制的从库.' % (self._host, self._port))
                #multi_tier_slave_info = [self._host, self._port, self._user, self._password]
                slave_info = [self._host, self._port, self._user, self._password]
            else:
                logging.error('\033[1;31m%s:%s - 这台机器你没有设置主从复制，退出主程序.\033[0m' % (self._host, self._port))
                sys.exit('MySQL Replication Health is NOT OK!')
        except pymysql.Error as e:
            print("Error %d: %s" % (e.args[0], e.args[1]))
            sys.exit('MySQL Replication Health is NOT OK!')
        finally:
            cursor.close()

        #return master_info, slave_info, multi_tier_slave_info
        return master_info, slave_info

    def get_slave_status(self):
        cursor = self._connection.cursor(cursor=pymysql.cursors.DictCursor)  # 以字典的形式返回操作结果
        try:
            is_slave = cursor.execute('SHOW SLAVE STATUS')
            r_dict = cursor.fetchone()

            if is_slave == 1:
                if r_dict['Slave_IO_Running'] == 'Yes' and r_dict['Slave_SQL_Running'] == 'Yes':
                    if r_dict['Seconds_Behind_Master'] == 0:
                        logging.info('\033[1;36m同步正常，无延迟. \033[0m')
                    else:
                        logging.info('同步正常，但有延迟，延迟时间为：%s' % r_dict['Seconds_Behind_Master'])
                else:
                    pass
                    logging.error('\033[1;31m主从复制报错，请检查. Slave_IO_Running状态值是：%s '
                                  ' |  Slave_SQL_Running状态值是：%s  \n  \tLast_Error错误信息是：%s'
                                  '  \n\n  \tLast_SQL_Error错误信息是：%s \033[0m' \
                                  % (r_dict['Slave_IO_Running'], r_dict['Slave_SQL_Running'], \
                                     r_dict['Last_Error'], r_dict['Last_SQL_Error']))
                    repl_error = cursor.execute('select LAST_ERROR_NUMBER,LAST_ERROR_MESSAGE,LAST_ERROR_TIMESTAMP '
                                                'from performance_schema.replication_applier_status_by_worker '
                                                'ORDER BY LAST_ERROR_TIMESTAMP desc limit 1')
                    error_dict = cursor.fetchone()
                    print('错误号是：%s' % error_dict['LAST_ERROR_NUMBER'])
                    print('错误信息是：%s' % error_dict['LAST_ERROR_MESSAGE'])
                    print('报错时间是：%s\n' % error_dict['LAST_ERROR_TIMESTAMP'])
                    sys.exit('MySQL Replication Health is NOT OK!')
                if r_dict['Auto_Position'] != 1:
                    print('你没有开启基于GTID全局事务ID复制，不符合高可用故障转移的基础环境，退出主程序.')
                    sys.exit('MySQL Replication Health is NOT OK!')
            else:
                pass

        except pymysql.Error as e:
            print("Error %d: %s" % (e.args[0], e.args[1]))
            sys.exit('MySQL Replication Health is NOT OK!')
        finally:
            cursor.close()

        return r_dict


###### End class MySQL_Check


#############################################################################################
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - [%(levelname)s] %(message)s',
                        datefmt='%a %b %d %H:%M:%S %Y')

    # 运行程序时必须加--conf=指定配置文件
    try:
        if sys.argv[1]:
            pass
    except IndexError:
        sys.exit('--conf=<server config file> must be set.')
    matchObj = re.search(r'^--conf=\S', sys.argv[1])
    if matchObj:
        cnf_file = sys.argv[1].replace('--conf=', '')
    else:
        print("No match!! --conf=")
        sys.exit('--conf=<server config file> must be set.')

    """
    # 检测cnf配置文件里是否含有finish标签，如果有，则证明主从复制环境正常，以避免二次检查，没有则进行检查
    parser_obj = configparser.RawConfigParser()
    parser_obj.read(cnf_file, encoding='utf-8')
    if parser_obj.has_section('finish'):
        sys.exit('你的主从复制环境已经检测完毕，是正常的，无需第二次复审.')
    """

    # 提取出主机信息， hosts_info_lis变量类型是列表
    hosts_info_list = Config_Parser.read_server(filename=cnf_file)
    ###### 第一步开始检测app1.cnf配置文件里设置是否正确，以及主从复制集群的健康检查 ######
    current_master = current_slave = []
    master_status = slave_status = candidate_master_status = 0
    master_count = slave_count = candidate_master_status = 0
    current_slave_ssh_info = []
    for i in hosts_info_list:
        if len(i) == 7:
            ip, port, user, password, ssh_user, ssh_password, ssh_port = i
        else:
            ip, port, user, password, ssh_user, ssh_password, ssh_port, candidate_master = i
        mysql_conn = MySQL_Check(host=ip, port=port, user=user, password=password)
        #master_status, master_info, slave_info, multi_tier_slave_info = mysql_conn.chek_repl_status()
        master_info, slave_info = mysql_conn.chek_repl_status()
        #print('master_info_list:', master_info)
        #print('slave_info_list:', slave_info)

        if master_info:
            master_status += 1
            if master_status > 1:
                logging.error('\033[1;31m怎么可能一个主从复制集群中有两个主库？！退出主程序，请重新核实你的环境. \033[0m')
                sys.exit('MySQL Replication Health is NOT OK!')
            else:
                current_master = master_info
        if slave_info:
            slave_count += 1
            var_exists = 'candidate_master' in locals()
            if var_exists:
                current_slave_ssh_info.append([ip, ssh_port, ssh_user, ssh_password, candidate_master])
            else:
                current_slave_ssh_info.append([ip, ssh_port, ssh_user, ssh_password])
            current_slave.append(slave_info)
            #if candidate_master:
            if var_exists:
                if candidate_master:
                    #print('candidate_master:',candidate_master)
                    print('当前候选主库ip是：%s, 已经开启选项candidate_master=%d' % (ip,candidate_master))
                    candidate_master_status += 1
                    if candidate_master_status >= 2:
                        logging.error('\033[1;31m怎么可能一个主从复制集群中设置两个候选主库？！退出主程序，请重新核实你的环境. \033[0m')
                        sys.exit('MySQL Replication Health is NOT OK!')
                    candidate_master = None

        # 第二步是检测show slave status，同步状态是否为双Yes状态，出现一个No，类方法直接抛出异常并且退出主程序
        mysql_conn.get_slave_status()

        print('')

    print('{0}({1}:{2})(current master)' .format(current_master[0], current_master[0], current_master[1]))
    for s_list in current_slave:
        print(' +--{0}({1}:{2})' .format(s_list[0], s_list[0], s_list[1]))
        #print('candidate_master:', candidate_master)
    
    # 第三步都检测完毕后，打印MySQL复制成功信息。
    print('')
    logging.info('MySQL Replication Health is OK.')

    ###### 以上完成主从复制健康检查 ######

    """
    # 第四步当通过健康检查后，对cnf配置文件最后一行追加一个标签finish
    parser_obj = configparser.RawConfigParser()
    parser_obj.add_section('finish')
    parser_obj.set('finish', 'check_finish', '1')
    with open(cnf_file, 'a') as configfile:
        configfile.write('\n')
        parser_obj.write(configfile)

    # 第五步对cnf配置文件更改权限444只读权限，防止人为修改，因为开启故障转移守护进程需要判断这个finish标签
    cmd = '/usr/bin/chmod 444 %s'
    r_chmod = os.system(cmd % cnf_file)
    if r_chmod == 0:
        print('\n配置文件: %s 已经更改为只读权限.' % cnf_file)
    else:
        print('\n配置文件: %s 更改为只读权限失败.' % cnf_file)
    """
################################## END ######################################
