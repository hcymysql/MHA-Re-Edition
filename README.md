# MHA-Re-Edition 

MySQL (MHA)重构版，由于MHA工具2018年已经停止维护更新，且不支持Gtid复制模式，固考虑将其重构。

参考了MHA的故障切换思想，改进的地方有：

1）无需开启ssh公私钥认证，只需在cnf配置文件里提供用户名和密码（root权限）即可，这一步的作用是漂移VIP，工具会直接进入远程主机上执行ip addr add VIP

2）目前主流版本MySQL 5.7和8.0的复制模式是基于Gtid，因事务号是唯一的，更改同步指向不需要知道binlog文件名和position位置点，固简化了在客户端部署agent做数据补齐。

3）无需安装，就两个文件，一个是（环境配置检查）可执行文件masterha_check_repl_mysql，一个是（故障自动转移auto failover和在线平滑切换switch）可执行文件masterha_manager_mysql

### 配置文件

#### app1.cnf

[DEFAULT]

#log日志目录和文件名

manager_workdir = /root/mha_log/app1.log 

vip = 172.19.136.200

interface = bond0

#监控间隔时间，单位秒

connect_interval=1

#开启调用其他从库去连接主库，如果不需要，则删除masterha_secondary_check这行内容

#脚本会调用从库的mysql命令，默认读取路径是/usr/bin/mysql（已经写死），如没有请创建一个软连接

masterha_secondary_check = 172.19.136.33,172.19.136.34

running_updates_limit = 60

[server1]

ip = 172.19.136.32

port = 3306

user = repl

password = sysrepl

ssh_user = root

ssh_port = 22

ssh_password = 123456

[server2]

ip = 172.19.136.33

port = 3307

user = repl

password = sysrepl

ssh_user = root

ssh_port = 22

ssh_password = 123456

candidate_master = 1

[server3]

ip = 172.19.136.34

port = 3308

user = repl

password = sysrepl

ssh_user = root

ssh_port = 22

ssh_password = 123456
