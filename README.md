# MHA-Re-Edition 

MySQL (MHA)重构版，由于MHA工具2018年已经停止维护更新，且不支持Gtid复制模式，固考虑将其重构。

参考了MHA的故障切换思路，改进的地方有：

1）无需打通ssh公私钥互信认证，只需在app1.cnf配置文件里提供用户名和密码（root权限）即可，这一步的作用是漂移VIP，工具会直接进入远程主机上执行ip addr add VIP

2）目前主流版本MySQL 5.7和8.0的复制模式是基于Gtid，因事务号是唯一的，更改同步复制源不需要知道binlog文件名和position位置点，固简化了在客户端部署agent做数据补齐。

3）无需安装，就两个文件，一个是（环境配置检查）可执行文件masterha_check_repl_mysql，一个是（故障自动转移auto failover和在线平滑切换switch）可执行文件masterha_manager_mysql

### 配置文件（请按照app1.cnf范例模板严丝合缝的去设置）

### 环境配置检查

###### shell> chmod 755 masterha_check_repl_mysql
###### shell> ./masterha_check_repl_mysql --conf=app1.cnf

### 开启守护进程，主库故障后，VIP自动故障转移，其他从库自动change master to 指向新主库
###### shell> chmod 755 masterha_manager_mysql
###### shell> ./masterha_manager_mysql --conf=app1.cnf start

### 故障切换的步骤：

1）MHA Re-Edition管理机每隔app1.cnf配置文件参数connect_interval=1（秒），去连接主库，当试图连接3次失败后，尝试去其他从库上去连接并执行select 1探测，这里需要你在app1.cnf配置文件里设置masterha_secondary_check = slave1,slave2

设置完后，slave1和slave2去连接，如果有一台从库可以连接到主库，不认定主库down掉，不进行故障转移操作，会在log日志中输出warning警告信息，提示网络有问题，请排查。

如果MHA Re-Edition管理机和其他slave从库都无法访问连接，则认定主库挂掉，开始进行故障切换。

2）如果你在app1.cnf配置文件里设置candidate_master = 1，指定了候选主库，则默认提升该新主库。

如果你没有在app1.cnf配置文件里设置candidate_master = 1，则根据从库执行的Gtid事件最新的将其提升为主库。

3）当从库出现延迟时，在app1.cnf配置文件里，超过参数running_updates_limit = 60 单位（秒）内，且未同步完数据，则强制开启VIP故障切换转移，并在log日志中输出warning警告信息。否则会一直等待60秒内执行完从库的Gtid事件。

4）其他从库会change master to改变同步源为候选主库，并在log日志中输出show master status新主库的状态信息。

5）关闭候选主库的set global super_read_only = 0只读权限

6）候选主库不执行reset slave all清空同步信息，这一步操作交给用户处理。

7）漂移VIP至新的主库。至此故障转移流程跑完。
