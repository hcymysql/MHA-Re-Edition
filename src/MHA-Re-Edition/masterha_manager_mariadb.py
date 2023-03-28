import os, sys, re, logging, configparser, atexit, signal
import pymysql, paramiko
from pymysql.constants import CLIENT
from masterha_check_repl_mariadb import Config_Parser, MariaDB_Check


class MasterFailover(object):
    def __init__(self, host, port, user, password):
        self._host = host
        self._port = int(port)
        self._user = user
        self._password = password
        self._connection = None
        self.m_connect_status = 0

    def check_connect(self):
        try:
            self._connection = pymysql.connect(host=self._host, port=self._port, user=self._user, passwd=self._password)
            self.m_connect_status = 1
        except pymysql.Error as e:
            self.m_connect_status = 0
            print("Error %d: %s" % (e.args[0], e.args[1]))
        return self.m_connect_status

    def get_slave_status(self):
        self._connection = pymysql.connect(host=self._host, port=self._port, user=self._user, passwd=self._password)
        cursor = self._connection.cursor(cursor=pymysql.cursors.DictCursor)  # 以字典的形式返回操作结果
        try:
            cursor.execute('SHOW SLAVE STATUS')
            slave_status_dict = cursor.fetchone()
        except pymysql.Error as e:
            print("Error %d: %s" % (e.args[0], e.args[1]))
        finally:
            cursor.close()

        return slave_status_dict

    def elect_new_master(self):
        self._connection = pymysql.connect(host=self._host, port=self._port, user=self._user, passwd=self._password)
        cursor = self._connection.cursor()
        try:
            gtid_sql = 'select @@global.gtid_current_pos'
            cursor.execute(gtid_sql)
            gtid_result = cursor.fetchone()
        except pymysql.Error as e:
            print("Error %d: %s" % (e.args[0], e.args[1]))
        finally:
            cursor.close()

        return gtid_result

    def Wait_for_executed_GTID(self,master_gtid_executed, timeout=60):
        self._connection = pymysql.connect(host=self._host, port=self._port, user=self._user, passwd=self._password)
        cursor = self._connection.cursor()
        try:
            wait_gtid_finish_sql = 'SELECT MASTER_GTID_WAIT(\'{0}\' , {1})'.format(master_gtid_executed, timeout)
            cursor.execute(wait_gtid_finish_sql)
            wait_gtid_result = cursor.fetchone()
        except pymysql.Error as e:
            print("Error %d: %s" % (e.args[0], e.args[1]))
        finally:
            cursor.close()

        return wait_gtid_result

    def unset_super_read_only(self):
        self._connection = pymysql.connect(host=self._host, port=self._port, user=self._user, passwd=self._password)
        cursor = self._connection.cursor()
        try:
            cursor.execute('SET GLOBAL READ_ONLY = 0')
        except pymysql.Error as e:
            print("Error %d: %s" % (e.args[0], e.args[1]))
            return False
        finally:
            cursor.close()
        return True

    def set_super_read_only(self):
        self._connection = pymysql.connect(host=self._host, port=self._port, user=self._user, passwd=self._password)
        cursor = self._connection.cursor()
        try:
            cursor.execute('SET GLOBAL READ_ONLY = 1')
        except pymysql.Error as e:
            print("Error %d: %s" % (e.args[0], e.args[1]))
            return False
        finally:
            cursor.close()
        return True

    def get_new_master_candidate_status(self):
        self._connection = pymysql.connect(host=self._host, port=self._port, user=self._user, passwd=self._password)
        cursor = self._connection.cursor(cursor=pymysql.cursors.DictCursor)  # 以字典的形式返回操作结果
        try:
            cursor.execute('SHOW MASTER STATUS')
            show_master_status_dict = cursor.fetchone()
        except pymysql.Error as e:
            print("Error %d: %s" % (e.args[0], e.args[1]))
        finally:
            cursor.close()

        return show_master_status_dict

    def get_new_master_gtid_status(self):
        self._connection = pymysql.connect(host=self._host, port=self._port, user=self._user, passwd=self._password)
        cursor = self._connection.cursor()
        try:
            cursor.execute('select @@global.gtid_binlog_pos, @@global.gtid_current_pos')
            show_master_gtid_list = cursor.fetchone()
        except pymysql.Error as e:
            print("Error %d: %s" % (e.args[0], e.args[1]))
        finally:
            cursor.close()

        return show_master_gtid_list

    def slave_change_master_to(self, new_master_ip, new_master_port):
        self._connection = pymysql.connect(host=self._host, port=self._port, user=self._user, passwd=self._password, client_flag=CLIENT.MULTI_STATEMENTS)
        cursor = self._connection.cursor()
        try:
            change_sql = 'STOP SLAVE; CHANGE MASTER TO MASTER_HOST=\'{0}\', MASTER_PORT={1}, master_use_gtid = current_pos; START SLAVE' .format(new_master_ip, new_master_port)
            cursor.execute(change_sql)
        except pymysql.Error as e:
            print("Error %d: %s" % (e.args[0], e.args[1]))
            return False
        finally:
            cursor.close()

        return True

    def slave_change_master_switch(self, new_master_ip, new_master_port, new_master_user, new_master_password):
        self._connection = pymysql.connect(host=self._host, port=self._port, user=self._user, passwd=self._password, client_flag=CLIENT.MULTI_STATEMENTS)
        cursor = self._connection.cursor()
        try:
            change_sql = 'STOP SLAVE; CHANGE MASTER TO MASTER_HOST=\'{0}\', MASTER_USER=\'{1}\', MASTER_PASSWORD=\'{' \
                         '2}\', MASTER_PORT={3}, master_use_gtid = current_pos; START SLAVE' \
                         .format(new_master_ip, new_master_user, new_master_password, new_master_port)
            cursor.execute(change_sql)
        except pymysql.Error as e:
            print("Error %d: %s" % (e.args[0], e.args[1]))
            return False
        finally:
            cursor.close()

        return True

    def ftwrl(self):
        self._connection = pymysql.connect(host=self._host, port=self._port, user=self._user, passwd=self._password)
        cursor = self._connection.cursor()
        try:
            ftwrl_sql = 'FLUSH TABLES WITH READ LOCK'
            cursor.execute(ftwrl_sql)
        except pymysql.Error as e:
            print("Error %d: %s" % (e.args[0], e.args[1]))
            return False
        finally:
            cursor.close()

        return True

    def unlock(self):
        self._connection = pymysql.connect(host=self._host, port=self._port, user=self._user, passwd=self._password)
        cursor = self._connection.cursor()
        try:
            unlock_sql = 'UNLOCK TABLES'
            cursor.execute(unlock_sql)
        except pymysql.Error as e:
            print("Error %d: %s" % (e.args[0], e.args[1]))
            return False
        finally:
            cursor.close()

        return True

    def ft(self):
        self._connection = pymysql.connect(host=self._host, port=self._port, user=self._user, passwd=self._password)
        cursor = self._connection.cursor()
        try:
            ft_sql = 'FLUSH NO_WRITE_TO_BINLOG TABLES'
            cursor.execute(ft_sql)
        except pymysql.Error as e:
            print("Error %d: %s" % (e.args[0], e.args[1]))
            return False
        finally:
            cursor.close()

        return True

    def get_kill_thread_id(self):
        self._connection = pymysql.connect(host=self._host, port=self._port, user=self._user, passwd=self._password)
        cursor = self._connection.cursor()  # 以字典的形式返回操作结果
        try:
            cursor.execute('select CONCAT(\'KILL \',ID) AS kill_list from information_schema.PROCESSLIST where TIME>=1 and COMMAND regexp \'^Query\'')
            get_kill_id = cursor.fetchall()
        except pymysql.Error as e:
            print("Error %d: %s" % (e.args[0], e.args[1]))
        finally:
            cursor.close()

        return get_kill_id

    def kill_thread_id(self, kill_sqls):
        self._connection = pymysql.connect(host=self._host, port=self._port, user=self._user, passwd=self._password)
        cursor = self._connection.cursor()
        try:
            cursor.execute(kill_sqls)
        except pymysql.Error as e:
            print("Error %d: %s" % (e.args[0], e.args[1]))
            return False
        finally:
            cursor.close()

        return True

    def stop_slave(self):
        self._connection = pymysql.connect(host=self._host, port=self._port, user=self._user, passwd=self._password, client_flag=CLIENT.MULTI_STATEMENTS)
        cursor = self._connection.cursor()
        try:
            stop_sql = 'STOP SLAVE'
            cursor.execute(stop_sql)
        except pymysql.Error as e:
            print("Error %d: %s" % (e.args[0], e.args[1]))
            return False
        finally:
            cursor.close()

        return True

######################################################################
# end class VipManager
######################################################################

class VipManager:
    def ssh_connect(self, ip, ssh_port, ssh_user, ssh_passwd):
        try:
            # 连接服务器
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(hostname=ip, port=ssh_port, username=ssh_user, password=ssh_passwd, banner_timeout=60,
                           timeout=10)
        except Exception as e:
            print('\x1b[1;31m主机：%s ssh连接失败!!! 错误信息：%s \x1b[0m' % (ip, str(e)))
        return client  # 返回client实例化对象

    def ssh_exec(self, ip, ssh_port, ssh_user, ssh_passwd, remote_cmd):
        # 把client对象赋值给变量ssh
        ssh = self.ssh_connect(ip, ssh_port, ssh_user, ssh_passwd)
        '''
        sudo使用方法
        https://stackoverflow.com/questions/6270677/how-to-run-sudo-with-paramiko-python
        https://codingdict.com/questions/169384
        '''
        sudo = '/usr/bin/sudo -S /bin/bash -c  '
        stdin, stdout, stderr = ssh.exec_command(sudo + '\'' + remote_cmd + '\'')
        stdin.write(ssh_passwd + '\n')  # 自动输入密码
        stdin.flush()
        ### 获取命令返回值 ###################
        channel = stdout.channel
        status = channel.recv_exit_status()
        ######################################
        '''
        # shell里0代表真，1代表假，Python里刚好相反。
        if status == 0:
            print(stdout.read().decode('utf-8'))
            print('检测到VIP地址已存在.')
        else:
            print('\x1b[1;31m执行命令: {0} 没有获取到该VIP地址，程序将自动添加. \x1b[0m'.format(remote_cmd))
            print(stderr.read().decode('utf-8'))
        '''
        # 关闭连接
        ssh.close()

        return status


######################################################################
# end class VipManager
######################################################################

def daemonize(pidfile, *, stdin='/dev/null',
              stdout='/dev/null',
              stderr='/dev/null'):
    if os.path.exists(pidfile):
        raise RuntimeError('Already running')

    # First fork (detaches from parent)
    try:
        if os.fork() > 0:
            raise SystemExit(0)  # Parent exit
    except OSError as e:
        raise RuntimeError('fork #1 failed.')

    # os.chdir('/')
    os.umask(0)
    os.setsid()
    # Second fork (relinquish session leadership)
    try:
        if os.fork() > 0:
            raise SystemExit(0)
    except OSError as e:
        raise RuntimeError('fork #2 failed.')

    # Flush I/O buffers
    sys.stdout.flush()
    sys.stderr.flush()

    # Replace file descriptors for stdin, stdout, and stderr
    with open(stdin, 'rb', 0) as f:
        os.dup2(f.fileno(), sys.stdin.fileno())
    with open(stdout, 'ab', 0) as f:
        os.dup2(f.fileno(), sys.stdout.fileno())
    with open(stderr, 'ab', 0) as f:
        os.dup2(f.fileno(), sys.stderr.fileno())

    # Write the PID file
    with open(pidfile, 'w') as f:
        print(os.getpid(), file=f)

    # Arrange to have the PID file removed on exit/signal
    atexit.register(lambda: os.remove(pidfile))

    # Signal handler for termination (required)
    def sigterm_handler(signo, frame):
        raise SystemExit(1)

    signal.signal(signal.SIGTERM, sigterm_handler)


###### End def daemonize ######

def MasterMonitor(cnf_file):
    import time
    # 提取出default公共配置信息
    server_default_dict = Config_Parser.read_default(filename=cnf_file)
    vip = server_default_dict['vip']
    interface = server_default_dict['interface']
    if server_default_dict.get('running_updates_limit'):
        running_updates_limit = server_default_dict['running_updates_limit']
    else:
        running_updates_limit = 60
    if server_default_dict.get('masterha_secondary_check'):
        masterha_secondary_check = tuple(server_default_dict['masterha_secondary_check'].split(','))
    else:
        masterha_secondary_check = None

    if server_default_dict.get('weixin_alarm'):
        weixin_alarm = server_default_dict['weixin_alarm']
    else:
        weixin_alarm = None

    if server_default_dict.get('shutdown_script'):
        shutdown_script = server_default_dict['shutdown_script']
    else:
        shutdown_script = None

    # 提取出server主机信息
    hosts_info_list = Config_Parser.read_server(filename=cnf_file)

    ###### 第一步开始检测app1.cnf配置文件里设置是否正确，以及主从复制集群的健康检查 ######
    current_master = current_slave = []
    master_count = slave_count = candidate_master_status = 0
    current_slave_ssh_info = current_master_ssh_info = []
    for i in hosts_info_list:
        if len(i) == 7:
            ip, port, user, password, ssh_user, ssh_password, ssh_port = i
        else:
            ip, port, user, password, ssh_user, ssh_password, ssh_port, candidate_master = i
        mysql_conn = MariaDB_Check(host=ip, port=port, user=user, password=password)
        # master_status, master_info, slave_info, multi_tier_slave_info = mysql_conn.chek_repl_status()
        master_info, slave_info = mysql_conn.chek_repl_status()

        if master_info:
            master_count += 1
            current_master_ssh_info = (ip, ssh_port, ssh_user, ssh_password)
            if master_count > 1:
                logging.error('\033[1;31m怎么可能一个主从复制集群中有两个主库？！退出主程序，请重新核实你的环境. \033[0m')
                sys.exit('MariaDB Replication Health is NOT OK!')
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
                    logging.info('当前候选主库ip是：%s, 已经开启选项candidate_master=%d' % (ip, candidate_master))
                    candidate_master_status += 1
                    if candidate_master_status >= 2:
                        logging.error('\033[1;31m怎么可能一个主从复制集群中设置两个候选主库？！退出主程序，请重新核实你的环境. \033[0m')
                        sys.exit('MariaDB Replication Health is NOT OK!')
                    candidate_master = None


        # 第二步是检测show slave status，同步状态是否为双Yes状态，出现一个No，类方法直接抛出异常并且退出主程序
        mysql_conn.get_slave_status()

        # 第三步，打开从库的只读权限super_read_only=1
        for current_slaves in current_slave:
            mysql_conn0 = MasterFailover(current_slaves[0], current_slaves[1], current_slaves[2], current_slaves[3])
            set_super_read_only_status = mysql_conn0.set_super_read_only()
            if set_super_read_only_status:
                logging.info('打开从库{0}:{1}的只读权限super_read_only=1成功.'.format(current_slaves[0], current_slaves[1]))
            else:
                logging.error('打开从库{0}:{1}的只读权限super_read_only=1失败.'.format(current_slaves[0], current_slaves[1]))

        print('')

    print('{0}({1}:{2})(current master)'.format(current_master[0], current_master[0], current_master[1]))
    for s_list in current_slave:
        print(' +--{0}({1}:{2})'.format(s_list[0], s_list[0], s_list[1]))
    ###### 以上完成主从复制健康检查 ######

    # 第四步检查当前主库的VIP是否设置，如果没有设置，则自动添加VIP
    # Centos6 /sbin/ip; Centos7 /usr/sbin/ip
    check_vip_cmd = "/usr/sbin/ip addr | grep '" + vip + "'"
    vipobj = VipManager()
    status = vipobj.ssh_exec(current_master_ssh_info[0], current_master_ssh_info[1],
                             current_master_ssh_info[2], current_master_ssh_info[3],
                             check_vip_cmd)
    # shell里0代表真，1代表假，Python里刚好相反。
    if status == 0:
        logging.info('\033[0;37;42m检测到VIP地址已存在.\033[0m')
    else:
        logging.info('\033[0;33;40m执行命令: {0} 没有获取到该VIP地址，程序将自动添加. \033[0m'.format(check_vip_cmd))
        mask = "24"
        add_vip_cmd = "/usr/sbin/ip addr add " + vip + "/" + mask + " dev " + interface + ";" \
                     "/usr/sbin/arping -q -c 2 -U -I " + interface + " " + vip
        status = vipobj.ssh_exec(current_master_ssh_info[0], current_master_ssh_info[1],
                                 current_master_ssh_info[2], current_master_ssh_info[3],
                                 add_vip_cmd)
        if status == 0:
            logging.info('\033[0;37;42m执行命令: {0} 成功添加该VIP地址. \033[0m'.format(add_vip_cmd))
        else:
            logging.error('\033[1;31m添加VIP失败，退出主程序，请检查错误日志. \033[0m')
            sys.exit(1)

    sys.stdout.write('Daemon started with pid {}\n'.format(os.getpid()))
    sys.stdout.write('Daemon Alive! {}\n'.format(time.ctime()))

    # 第五步，开启一个死循环，监控主库端口的存活状态
    m_connect_error_count = 0
    master_dead_confirm = None
    ok_count = 0
    while True:
        ok_count += 1
        #vip1 = '172.19.136.203'
        mysql_conn = MasterFailover(vip, current_master[1], current_master[2], current_master[3])
        m_connect_status = mysql_conn.check_connect()
        if m_connect_status == 1:
            for i in range(1):
                if ok_count < 2:
                    logging.info('{0}:{1} 主库目前状态OK'. format(current_master[0], current_master[1]))
            time.sleep(int(server_default_dict['connect_interval']))
        if m_connect_status == 0:
            m_connect_error_count += 1
            if 1 <= m_connect_error_count < 3:
                logging.warning('网络可能存在丢包，继续尝试连接主库.\n')
            if m_connect_error_count >= 3:
                logging.error('\033[1;31m主库尝试连接3次后继续失败.\033[0m')
                if masterha_secondary_check:
                    logging.info('现在准备调用 masterha_secondary_check参数去其他从库尝试连接主库.')
                    for secondary_ip in masterha_secondary_check:
                        for s_list in current_slave_ssh_info:
                            if secondary_ip in s_list:
                                from_slave_connect_master_cmd = "/usr/bin/mysql -h{0} -p{1} -u{2} -p{3} -e \"select 1\""  \
                                      .format(vip, current_master[1], current_master[2], current_master[3])
                                status = vipobj.ssh_exec(s_list[0], s_list[1],s_list[2], s_list[3],from_slave_connect_master_cmd)
                                if status == 0:
                                    logging.warning('\033[0;37;42m 在从库机器（{}）上可以连接主库，网络确定存在问题，'
                                          '不进行切换，请直接通知网络工程师排查问题. \033[0m'.format(secondary_ip))
                                    master_dead_confirm = 'on'
                                else:
                                    logging.error('\033[1;31m在从库机器（{}）上也无法连接主库，已确认主库已经彻底挂掉，现在进行自动故障切换. \033[0m'.format(secondary_ip))
                                    master_dead_confirm = 'down'
                if not masterha_secondary_check or master_dead_confirm == 'down':
                    # 第六步，确认主库已经死掉，切换开始
                    # 先试图去把主库的VIP给卸载掉
                    mask = "24"
                    del_vip_cmd = "/usr/sbin/ip addr del " + vip + "/" + mask + " dev " + interface
                    try:
                        status = vipobj.ssh_exec(current_master_ssh_info[0], current_master_ssh_info[1],
                                             current_master_ssh_info[2], current_master_ssh_info[3],
                                             del_vip_cmd)
                    except Exception as e:
                        print('\x1b[1;31m主库：%s 无法ping通!!! \x1b[0m' % current_master[0])

                    if status == 0:
                        logging.info('\033[0;37;42m执行命令: {0} 成功删除该VIP地址. \033[0m'.format(del_vip_cmd))
                    else:
                        logging.error('\033[1;31m删除VIP失败，主机已经hang住，只能通过远程管理卡去重启机器.\n \
                                在这里你可以调用远控卡命令，比如DELL服务器的ipmitool命令\n  \
                               # 重启电源\n \
                                shell> ipmitool -I lanplus -H 服务器IP -U 远程console用户 -P 远程console密码 power reset \
                        \033[0m')
                        if shutdown_script is not None:
                            os.system(shutdown_script)

                    # 第七步，选举一个候选主库
                    # 如果用户在配置文件里指定了候选主库，那则以该台主机作为故障切换后的新主库
                    new_master_candidate_ssh_info = []
                    for is_set in hosts_info_list:
                        if len(is_set) == 8:
                            logging.info('在配置文件里指定了候选主库，那则以该台主机作为故障切换后的新主库\n')
                            #max_index = hosts_info_list.index(max(hosts_info_list, key=len))
                            new_master_candidate_ssh_info = is_set

                    if len(new_master_candidate_ssh_info) != 0:
                        new_master_candidate = [new_master_candidate_ssh_info[0], new_master_candidate_ssh_info[1]]
                        logging.info('新的主库候选人是 ==> : {0}:{1}'. format(new_master_candidate[0], new_master_candidate[1]))
                    else:
                        logging.info('没有在配置文件里找到candidate_master=1参数，则以最新的Gtid作为故障切换后的新主库\n')
                        new_master_info = []
                        for s in current_slave:
                            mysql_conn2 = MasterFailover(s[0], s[1], s[2], s[3])
                            slave_status_dict = mysql_conn2.get_slave_status()
                            master_gtid_executed = slave_status_dict['Gtid_IO_Pos'].replace('\n','')
                            #slave_gtid_executed = slave_status_dict['Executed_Gtid_Set'].replace('\n','')
                            gtid_result = mysql_conn2.elect_new_master()
                            for mariadb_gtid in gtid_result:
                                if mariadb_gtid == master_gtid_executed:
                                    new_master_info.append([0, mariadb_gtid, s[0], s[1]])
                                else:
                                    new_master_info.append([-1, mariadb_gtid, s[0], s[1]])
                        tmp_count = 0
                        for i in new_master_info:
                            count = i.count(0)
                            tmp_count = tmp_count + count
                        if tmp_count >= 2:
                            # 如果同步复制都执行完，则取配置文件里server最靠前的主机作为候选主库
                            new_master_candidate = [new_master_info[0][2], new_master_info[0][3]]
                            logging.info('新的主库候选人是 ==> : {0}:{1}'. format(new_master_candidate[0], new_master_candidate[1]))
                        else:
                            #new_master_info_sort = sorted(new_master_info, reverse=True)
                            new_master_info_sort = sorted(new_master_info) # 选举GTID最新的候选主库
                            new_master_candidate_tmp = new_master_info_sort[0]
                            new_master_candidate = [new_master_candidate_tmp[2], new_master_candidate_tmp[3]]
                            logging.info('新的主库候选人是 ==> : {0}:{1}'. format(new_master_candidate[0], new_master_candidate[1]))

                    other_slave = new_master = []
                    for cs in current_slave:
                        if new_master_candidate[0] != cs[0] and new_master_candidate[1] != cs[1]:
                            other_slave.append(cs)
                    for nm in current_slave:
                        if new_master_candidate[0] == nm[0] and new_master_candidate[1] == nm[1]:
                            new_master = nm  # 得到备选主库的MySQL信息
                    for other_slaves in other_slave:
                        logging.info('其他从库的信息是：{0}:{1}'. format(other_slaves[0], other_slaves[1]))
                    #print('new_master =>', new_master)

                    new_master_ssh_info = []
                    for slave_ssh in current_slave_ssh_info:
                        if new_master[0] == slave_ssh[0]:
                            new_master_ssh_info = slave_ssh
                    #print('备选主库的ssh信息是: ', new_master_ssh_info)

                    # 第八步是关键，等待从库执行完剩余的GTID事件后，提升为新主库
                    for is_set in hosts_info_list:
                        if len(is_set) == 8:
                            new_master_candidate_ssh_info = is_set
                    if len(new_master_candidate_ssh_info) != 0:
                        mysql_conn_wait = MasterFailover(new_master_candidate_ssh_info[0], new_master_candidate_ssh_info[1],
                                                         new_master_candidate_ssh_info[2], new_master_candidate_ssh_info[3])
                        slave_status_dict = mysql_conn_wait.get_slave_status()
                        master_gtid_executed = slave_status_dict['Gtid_IO_Pos'].replace('\n', '')
                        timeout = running_updates_limit
                        wait_gtid_result = mysql_conn_wait.Wait_for_executed_GTID(master_gtid_executed, timeout)
                    else:
                        mysql_conn_wait = MasterFailover(new_master[0], new_master[1],
                                                         new_master[2], new_master[3])
                        slave_status_dict = mysql_conn_wait.get_slave_status()
                        master_gtid_executed = slave_status_dict['Gtid_IO_Pos'].replace('\n', '')
                        timeout = running_updates_limit
                        wait_gtid_result = mysql_conn_wait.Wait_for_executed_GTID(master_gtid_executed, timeout)
                    for i in wait_gtid_result:
                        if i == 0:
                            logging.info('数据已经同步完毕，开始进行切换.')
                        else:
                            logging.warning('候选主库：{0}  端口：{1}，在你设置的{2}秒内数据没有同步完毕，这是你自己设置的时间，切换后数据会出现不一致，'
                                  '我已经做到了提前告知义务，你应该自己去审查从库为什么会出现延迟问题。'
                                  'Sorry，程序现在开始进行切换.'
                                  .format(new_master_candidate[0], new_master_candidate[1], timeout))

                    # 第九步，得到新主库的show master staus信息
                    mysql_conn_new_master = MasterFailover(new_master[0], new_master[1], new_master[2], new_master[3])
                    new_master_candidate_status_dict = mysql_conn_new_master.get_new_master_candidate_status()
                    show_master_gtid_list = mysql_conn_new_master.get_new_master_gtid_status()
                    logging.info('新主库{0}:{1} show master status信息是：'. format(new_master[0], new_master[1]))
                    logging.info('File: {0}'. format(new_master_candidate_status_dict['File']))
                    logging.info('Position: {0}'. format(new_master_candidate_status_dict['Position']))
                    logging.info('Binlog_Do_DB: {0}'. format(new_master_candidate_status_dict['Binlog_Do_DB']))
                    logging.info('Binlog_Ignore_DB: {0}'. format(new_master_candidate_status_dict['Binlog_Ignore_DB']))
                    logging.info('gtid_binlog_pos: {0}'. format(show_master_gtid_list[0]))
                    logging.info('gtid_current_pos: {0}'. format(show_master_gtid_list[1]))
                    #logging.info('Executed_Gtid_Set: {0}'. format(new_master_candidate_status_dict['Executed_Gtid_Set'].replace('\n', '')))
                    logging.info('你应该复制这句命令，在源主库恢复后，执行它并重新加入新集群里。')
                    logging.info('STOP SLAVE; CHANGE MASTER TO MASTER_HOST=\'{0}\', MASTER_USER=\'{1}\', MASTER_PASSWORD=\'{2}\', '
                                 'MASTER_PORT={3}, master_use_gtid=current_pos; START SLAVE;'
                                 . format(new_master[0], new_master[2], new_master[3], new_master[1]))

                    # 第十步，改变同步复制源，change master to指向新的主库
                    for slaves in other_slave:
                        mysql_conn_other_slave = MasterFailover(slaves[0], slaves[1], slaves[2], slaves[3])
                        change_status = mysql_conn_other_slave.slave_change_master_to(new_master[0], new_master[1])
                        #change_status = mysql_conn_other_slave.slave_change_master_switch(new_master[0], new_master[1], new_master[2], new_master[3])
                        if change_status:
                            logging.info('从库 - {0}:{1} CHANGE MASTER TO 指向新主库 - {2}:{3} 成功.' .format(slaves[0], slaves[1], new_master[0], new_master[1]))
                        else:
                            logging.info('从库 - {0}:{1} CHANGE MASTER TO 指向新主库 - {2}:{3} 失败.'.format(slaves[0], slaves[1], new_master[0], new_master[1]))

                    # 第十一步，关闭新主库只读权限
                    mysql_conn_new = MasterFailover(new_master[0],new_master[1],new_master[2],new_master[3])
                    unset_super_read_only_status = mysql_conn_new.unset_super_read_only()
                    if unset_super_read_only_status:
                        logging.info('关闭新主库{0}:{1}的只读权限super_read_only=0成功.' .format(new_master[0], new_master[1]))
                    else:
                        logging.error('关闭新主库{0}:{1}的只读权限super_read_only=0失败.' .format(new_master[0], new_master[1]))

                    # 第十二步，飘移VIP在新主库上生效，对外提供业务服务，到此，整体故障切换完成。
                    mask = "24"
                    addnew_vip_cmd = "/usr/sbin/ip addr add " + vip + "/" + mask + " dev " + interface + ";" \
                                    "/usr/sbin/arping -q -c 2 -U -I " + interface + " " + vip
                    vip_status = vipobj.ssh_exec(new_master_ssh_info[0], new_master_ssh_info[1],
                                             new_master_ssh_info[2], new_master_ssh_info[3],
                                             addnew_vip_cmd)
                    if vip_status == 0:
                        logging.info('\033[0;37;42m执行命令: {0} 成功添加该VIP地址. \033[0m'.format(addnew_vip_cmd))
                        if not weixin_alarm is None:
                            #  pip install simplejson -i  "http://mirrors.aliyun.com/pypi/simple"  --trusted-host "mirrors.aliyun.com"
                            create_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                            send_weixin_alarm = '{0}  \'源主库{1}:{2}已经挂掉\'  \'候选主库{3}:{4}已经切换完毕，目前是新主库，vip已经漂移成功. - {5}\'' \
                                .format(weixin_alarm, current_master[0], current_master[1], new_master_candidate[0], new_master_candidate[1], create_time)
                            #logging.info(send_weixin_alarm)
                            os.system(send_weixin_alarm)
                        sys.exit('\n至此故障切换已经完毕，退出主程序，等待DBA修复挂掉的源主库并加入新集群里。感谢您的使用，祝您工作顺利。')
                    else:
                        logging.error('\033[1;31m添加VIP失败，请检查错误日志. \033[0m')
                        create_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                        send_weixin_alarm = '{0}  \'源主库{1}:{2}已经挂掉\'  \'候选主库{3}:{4}切换失败，vip漂移失败. - {5}\'' \
                            .format(weixin_alarm, current_master[0], current_master[1], new_master_candidate[0],
                                    new_master_candidate[1], create_time)
                        logging.error(send_weixin_alarm)
                        os.system(send_weixin_alarm)
                        sys.exit('\n至此故障切换已经完毕，退出主程序，等待DBA修复挂掉的源主库并加入新集群里。感谢您的使用，祝您工作顺利。')

                    # 第十三步，退出主程序，并发报警微信通止给DBA

###### End def MasterMonitor ######

def Online_Switch(cnf_file):
    import time
    # 提取出default公共配置信息
    server_default_dict = Config_Parser.read_default(filename=cnf_file)
    vip = server_default_dict['vip']
    interface = server_default_dict['interface']
    if server_default_dict.get('running_updates_limit'):
        running_updates_limit = server_default_dict['running_updates_limit']
    else:
        running_updates_limit = 60
    if server_default_dict.get('masterha_secondary_check'):
        masterha_secondary_check = tuple(server_default_dict['masterha_secondary_check'].split(','))
    else:
        masterha_secondary_check = None

    # 提取出server主机信息
    hosts_info_list = Config_Parser.read_server(filename=cnf_file)

    ###### 第一步开始检测app1.cnf配置文件里设置是否正确，以及主从复制集群的健康检查 ######
    current_master = current_slave = []
    master_count = slave_count = candidate_master_status = 0
    current_slave_ssh_info = []
    for i in hosts_info_list:
        if len(i) == 7:
            ip, port, user, password, ssh_user, ssh_password, ssh_port = i
        else:
            ip, port, user, password, ssh_user, ssh_password, ssh_port, candidate_master = i
        mysql_conn = MariaDB_Check(host=ip, port=port, user=user, password=password)
        # master_status, master_info, slave_info, multi_tier_slave_info = mysql_conn.chek_repl_status()
        master_info, slave_info = mysql_conn.chek_repl_status()

        if master_info:
            master_count += 1
            current_master_ssh_info = (ip, ssh_port, ssh_user, ssh_password)
            if master_count > 1:
                logging.error('\033[1;31m怎么可能一个主从复制集群中有两个主库？！退出主程序，请重新核实你的环境. \033[0m')
                sys.exit('MariaDB Replication Health is NOT OK!')
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
                    logging.info('当前候选主库ip是：%s, 已经开启选项candidate_master=%d' % (ip, candidate_master))
                    candidate_master_status += 1
                    if candidate_master_status >= 2:
                        logging.error('\033[1;31m怎么可能一个主从复制集群中设置两个候选主库？！退出主程序，请重新核实你的环境. \033[0m')
                        sys.exit('MariaDB Replication Health is NOT OK!')
                    candidate_master = None


        # 第二步是检测show slave status，同步状态是否为双Yes状态，出现一个No，类方法直接抛出异常并且退出主程序
        mysql_conn.get_slave_status()

    print('{0}({1}:{2})(current master)'.format(current_master[0], current_master[0], current_master[1]))
    for s_list in current_slave:
        print(' +--{0}({1}:{2})'.format(s_list[0], s_list[0], s_list[1]))
    ###### 以上完成主从复制健康检查 ######

    # 第四步，选举一个候选主库
    # 如果用户在配置文件里指定了候选主库，那则以该台主机作为故障切换后的新主库
    new_master_candidate_ssh_info = []
    for is_set in hosts_info_list:
        if len(is_set) == 8:
            logging.info('在配置文件里指定了候选主库，那则以该台主机作为故障切换后的新主库\n')
            # max_index = hosts_info_list.index(max(hosts_info_list, key=len))
            new_master_candidate_ssh_info = is_set

    if len(new_master_candidate_ssh_info) != 0:
        new_master_candidate = [new_master_candidate_ssh_info[0], new_master_candidate_ssh_info[1]]
        logging.info('新的主库候选人是 ==> : {0}:{1}'.format(new_master_candidate[0], new_master_candidate[1]))
        mysql_conn2 = MasterFailover(new_master_candidate_ssh_info[0], new_master_candidate_ssh_info[1],
                                     new_master_candidate_ssh_info[2], new_master_candidate_ssh_info[3])
        slave_status_dict = mysql_conn2.get_slave_status()
        master_gtid_executed = slave_status_dict['Gtid_IO_Pos'].replace('\n', '')
    else:
        logging.info('没有在配置文件里找到candidate_master=1参数，则以最新的Gtid作为故障切换后的新主库\n')
        new_master_info = []
        for s in current_slave:
            mysql_conn2 = MasterFailover(s[0], s[1], s[2], s[3])
            slave_status_dict = mysql_conn2.get_slave_status()
            master_gtid_executed = slave_status_dict['Gtid_IO_Pos'].replace('\n', '')
            #slave_gtid_executed = slave_status_dict['Executed_Gtid_Set'].replace('\n', '')
            gtid_result = mysql_conn2.elect_new_master()
            for mariadb_gtid in gtid_result:
                if mariadb_gtid == master_gtid_executed:
                    new_master_info.append([0, mariadb_gtid, s[0], s[1]])
                else:
                    new_master_info.append([-1, mariadb_gtid, s[0], s[1]])
        tmp_count = 0
        for i in new_master_info:
            count = i.count(0)
            tmp_count = tmp_count + count
        if tmp_count >= 2:
            # 如果同步复制都执行完，则取配置文件里server最靠前的主机作为候选主库
            new_master_candidate = [new_master_info[0][2], new_master_info[0][3]]
            logging.info('新的主库候选人是 ==> : {0}:{1}'.format(new_master_candidate[0], new_master_candidate[1]))
        else:
            #new_master_info_sort = sorted(new_master_info, reverse=True)
            new_master_info_sort = sorted(new_master_info) # 选举GTID最新的候选主库
            new_master_candidate_tmp = new_master_info_sort[0]
            new_master_candidate = [new_master_candidate_tmp[2], new_master_candidate_tmp[3]]
            logging.info('新的主库候选人是 ==> : {0}:{1}'.format(new_master_candidate[0], new_master_candidate[1]))

    other_slave = new_master = []
    for cs in current_slave:
        if new_master_candidate[0] != cs[0] and new_master_candidate[1] != cs[1]:
            other_slave.append(cs)
    for nm in current_slave:
        if new_master_candidate[0] == nm[0] and new_master_candidate[1] == nm[1]:
            new_master = nm  # 得到备选主库的MySQL信息
    for other_slaves in other_slave:
        logging.info('其他从库的信息是：{0}:{1}'.format(other_slaves[0], other_slaves[1]))
    # print('new_master =>', new_master)

    new_master_ssh_info = []
    for slave_ssh in current_slave_ssh_info:
        if new_master[0] == slave_ssh[0]:
            new_master_ssh_info = slave_ssh
    # print('备选主库的ssh信息是: ', new_master_ssh_info)

    # 第五步，源主库强制把打开的表关闭，这一步会耗费很长时间，尤其是业务繁忙的时候，请务必在凌晨执行。
    print('\n')
    while True:
        info_seq1 = '主库({0}:{1})在执行Online Switch在线平滑切换前，需要执行命令FLUSH NO_WRITE_TO_BINLOG TABLES，将会强制把打开的表关闭，' \
                    '这一步会耗费很长时间，尤其是业务繁忙的时候，请务必在凌晨执行。确定在主库({2}:{3})上执行吗？(YES/no): ' \
                    .format(current_master[0], current_master[1], current_master[0], current_master[1])
        x = input(info_seq1)
        if x.lower() == 'yes':
            logging.info('Switching is OK!')
            break
        elif x.lower() == 'no':
            logging.info('不进行切换.')
            sys.exit(1)
        elif x.lower() != 'yes' or x.lower() != 'no':
            logging.warning('用户输入的内容未识别.\n')
            continue
        else:
            pass

    logging.info('Executing FLUSH NO_WRITE_TO_BINLOG TABLES. This may take long time...')

    # 在原主库上执行
    mysql_conn_switch = MasterFailover(current_master[0], current_master[1], current_master[2], current_master[3])
    ft_status = mysql_conn_switch.ft()
    if ft_status:
        logging.info('主库 - {0}:{1} 执行命令 FLUSH NO_WRITE_TO_BINLOG TABLES 成功.' .format(current_master[0], current_master[1]))
    else:
        logging.info('主库 - {0}:{1} 执行命令 FLUSH NO_WRITE_TO_BINLOG TABLES 失败.' .format(current_master[0], current_master[1]))

    print('\n')
    while True:
        info_seq2 = 'Starting master switch from 主库({0}:{1}) to 候选主库({2}:{3})? (YES/no): ' \
            .format(current_master[0], current_master[1], new_master_candidate[0], new_master_candidate[1])
        x = input(info_seq2)
        if x.lower() == 'yes':
            logging.info('OK! 选择候选主库{0}:{1}'. format(new_master_candidate[0], new_master_candidate[1]))
            break
        elif x.lower() == 'no':
            logging.info('NO! 不选择候选主库{0}:{1}'. format(new_master_candidate[0], new_master_candidate[1]))
            sys.exit(1)
        elif x.lower() != 'yes' or x.lower() != 'no':
            logging.warning('用户输入的内容未识别.\n')
            continue
        else:
            pass

    print('\n')

    set_super_read_only_status = mysql_conn_switch.set_super_read_only()
    if set_super_read_only_status:
        logging.info('打开主库{0}:{1}的只读权限super_read_only=1成功.' .format(current_master[0], current_master[1]))
    else:
        logging.error('打开主库{0}:{1}的只读权限super_read_only=1失败.' .format(current_master[0], current_master[1]))

    # https://bugs.mysql.com/bug.php?id=106553
    get_kill_id = mysql_conn_switch.get_kill_thread_id()
    if not get_kill_id:
        logging.info('主库目前没有活动连接，无需kill掉应用连接的线程')
    else:
        for kill_id in get_kill_id:
            logging.info('正在kill掉线程thread_id: {0}'. format(kill_id[0]))
            mysql_conn_switch.kill_thread_id(kill_id[0])

    logging.info('Executing FLUSH TABLES WITH READ LOCK. This may take long time...')

    mysql_conn_switch.ftwrl()

    # 第六步，在候选主库上等待Gtid事件执行完
    mysql_conn_switch_candidate = MasterFailover(new_master[0], new_master[1], new_master[2], new_master[3])
    timeout = running_updates_limit
    wait_gtid_result = mysql_conn_switch_candidate.Wait_for_executed_GTID(master_gtid_executed, timeout)
    for i in wait_gtid_result:
        if i == 0:
            logging.info('数据已经同步完毕，开始进行切换.')
        else:
            logging.warning('候选主库：{0}  端口：{1}，在你设置的{2}秒内数据没有同步完毕，这是你自己设置的时间，切换后数据会出现不一致，'
                            '我已经做到了提前告知义务，你应该自己去审查从库为什么会出现延迟问题。'
                            'Sorry，程序现在开始进行切换.'
                            .format(new_master_candidate[0], new_master_candidate[1], timeout))

    # 第七步，得到候选主库的show master staus信息
    mysql_conn_new_master = MasterFailover(new_master[0], new_master[1], new_master[2], new_master[3])
    new_master_candidate_status_dict = mysql_conn_new_master.get_new_master_candidate_status()
    show_master_gtid_list = mysql_conn_new_master.get_new_master_gtid_status()
    logging.info('新主库{0}:{1} show master status信息是：'.format(new_master[0], new_master[1]))
    logging.info('File: {0}'.format(new_master_candidate_status_dict['File']))
    logging.info('Position: {0}'.format(new_master_candidate_status_dict['Position']))
    logging.info('Binlog_Do_DB: {0}'.format(new_master_candidate_status_dict['Binlog_Do_DB']))
    logging.info('Binlog_Ignore_DB: {0}'.format(new_master_candidate_status_dict['Binlog_Ignore_DB']))
    #logging.info('Executed_Gtid_Set: {0}'.format(new_master_candidate_status_dict['Executed_Gtid_Set'].replace('\n', '')))
    logging.info('gtid_binlog_pos: {0}'.format(show_master_gtid_list[0]))
    logging.info('gtid_current_pos: {0}'.format(show_master_gtid_list[1]))

    # 第八步，改变同步复制源，从库change master to指向新的主库
    for slaves in other_slave:
        mysql_conn_other_slave = MasterFailover(slaves[0], slaves[1], slaves[2], slaves[3])
        change_status = mysql_conn_other_slave.slave_change_master_to(new_master[0], new_master[1])
        if change_status:
            logging.info(
                '从库 - {0}:{1} CHANGE MASTER TO 指向新主库 - {2}:{3} 成功.'.format(slaves[0], slaves[1], new_master[0],
                                                                           new_master[1]))
        else:
            logging.info(
                '从库 - {0}:{1} CHANGE MASTER TO 指向新主库 - {2}:{3} 失败.'.format(slaves[0], slaves[1], new_master[0],
                                                                           new_master[1]))

    # 第九步，在源主库上解除锁表UNLOCK TABLES
    mysql_conn_switch.unlock()

    # 第十步，改变同步复制源，源主库change master to指向新的主库
    origin_status = mysql_conn_switch.slave_change_master_switch(new_master[0], new_master[1], new_master[2], new_master[3])
    if origin_status:
        logging.info(
            '源主库 - {0}:{1} CHANGE MASTER TO 指向新主库 - {2}:{3} 成功.'.format(current_master[0], current_master[1], new_master[0],
                                                                       new_master[1]))
    else:
        logging.info(
            '源主库 - {0}:{1} CHANGE MASTER TO 指向新主库 - {2}:{3} 失败.'.format(current_master[0], current_master[1], new_master[0],
                                                                       new_master[1]))
    # 第十一步，打开源主库只读权限
    mysql_conn_switch.set_super_read_only()

    # 第十二步，关闭候选主库同步复制 STOP SLAVE 但不执行RESET SLAVE ALL，这一步交给用户处理。
    mysql_conn_new_master.stop_slave()

    # 第十三步，关闭新主库只读权限
    mysql_conn_new = MasterFailover(new_master[0], new_master[1], new_master[2], new_master[3])
    unset_super_read_only_status = mysql_conn_new.unset_super_read_only()
    if unset_super_read_only_status:
        logging.info('关闭新主库{0}:{1}的只读权限super_read_only=0成功.'.format(new_master[0], new_master[1]))
    else:
        logging.error('关闭新主库{0}:{1}的只读权限super_read_only=0失败.'.format(new_master[0], new_master[1]))

    # 第十五步，把源主库的VIP给卸载掉
    # current_master_ssh_info
    vipobj = VipManager()
    mask = "24"
    del_vip_cmd = "/usr/sbin/ip addr del " + vip + "/" + mask + " dev " + interface
    status = vipobj.ssh_exec(current_master_ssh_info[0], current_master_ssh_info[1],
                             current_master_ssh_info[2], current_master_ssh_info[3],
                             del_vip_cmd)
    if status == 0:
        logging.info('\033[0;37;42m执行命令: {0} 成功删除该VIP地址. \033[0m'.format(del_vip_cmd))
    else:
        logging.error('\033[1;31m删除VIP失败.\033[0m')

    # 第十六步，飘移VIP在新主库上生效，对外提供业务服务，到此，整体故障切换完成。
    mask = "24"
    addnew_vip_cmd = "/usr/sbin/ip addr add " + vip + "/" + mask + " dev " + interface + ";" \
                      "/usr/sbin/arping -q -c 2 -U -I " + interface + " " + vip
    vip_status = vipobj.ssh_exec(new_master_ssh_info[0], new_master_ssh_info[1],
                                 new_master_ssh_info[2], new_master_ssh_info[3],
                                 addnew_vip_cmd)
    if vip_status == 0:
        logging.info('\033[0;37;42m执行命令: {0} 成功添加该VIP地址. \033[0m'.format(addnew_vip_cmd))
        sys.exit('\n至此Online master switch在线平滑切换已经完毕，退出主程序。感谢您的使用，祝您工作顺利。')
    else:
        logging.error('\033[1;31m添加VIP失败，请检查错误日志. \033[0m')
        sys.exit('\n至此Online master switch在线平滑切换已经完毕，退出主程序。感谢您的使用，祝您工作顺利。')

    # 第十七步，退出主程序，并发报警微信通止给DBA

###################################################################################################################
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - [%(levelname)s] %(message)s',
                        datefmt='%a %b %d %H:%M:%S %Y')

    if len(sys.argv) != 3:
        print('Usage: ./masterha_manager --conf=<server config file> [start|stop|status|switch]', file=sys.stderr)
        raise SystemExit(1)

    try:
        if sys.argv[1]:
            pass
    except IndexError:
        sys.exit('--conf=<server config file> must be set.')

    matchObj = re.search(r'^--conf=\S', sys.argv[1])
    if matchObj:
        cnf_file_tmp = sys.argv[1].replace('--conf=', '')
        filepath, cnf_file = os.path.split(cnf_file_tmp)
    else:
        print("No match!! --conf=")
        sys.exit('--conf=<server config file> must be set.')

    PIDFILE = '/tmp/daemon_{0}.pid'. format(cnf_file)

    server_default_dict = Config_Parser.read_default(filename=cnf_file)
    if server_default_dict.get('manager_workdir'):
        manager_workdir_logfile = server_default_dict['manager_workdir']
    else:
        manager_workdir_logfile = '/tmp/daemon_{0}.log'.format(cnf_file)

    if sys.argv[1] and sys.argv[2] == 'start':
        with open(manager_workdir_logfile, 'w') as f:
            f.write('启动后台守护进程.\n')
        try:
            daemonize(PIDFILE,
                      stdout=manager_workdir_logfile,
                      stderr=manager_workdir_logfile)
        except RuntimeError as e:
            print(e, file=sys.stderr)
            raise SystemExit(1)

        MasterMonitor(cnf_file)

    elif sys.argv[1] and sys.argv[2] == 'stop':
        if os.path.exists(PIDFILE):
            with open(PIDFILE) as f:
                os.kill(int(f.read()), signal.SIGTERM)
        else:
            print('Not running', file=sys.stderr)
            raise SystemExit(1)

    elif sys.argv[1] and sys.argv[2] == 'status':
        if os.path.exists(PIDFILE):
            with open(PIDFILE, mode='r') as f:
                pid_data = f.read()
                print('Is running. PID is: {0}' . format(pid_data.replace('\n','')))
        else:
            print('Not running', file=sys.stderr)
            raise SystemExit(1)

    elif sys.argv[1] and sys.argv[2] == 'switch':
        if os.path.exists(PIDFILE):
            with open(PIDFILE) as f:
                os.kill(int(f.read()), signal.SIGTERM)
        # else:
        #     print('Not running', file=sys.stderr)
        #     #raise SystemExit(1)
        Online_Switch(cnf_file)

    else:
        print('Unknown command {!r}'.format(sys.argv[2]), file=sys.stderr)
        raise SystemExit(1)
