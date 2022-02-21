# MHA-Re-Edition 

MySQL (MHA)重构版，由于MHA工具2018年已经停止维护更新，且不支持Gtid复制模式，固考虑将其重构。

参考了MHA的故障切换思想，改进的地方有：

1）无需开启ssh公私钥认证，只需在cnf配置文件里提供用户名和密码（root权限）即可，这一步的作用是漂移VIP，工具会直接进入远程主机上执行ip addr add VIP

2）目前主流版本MySQL 5.7和8.0的复制模式是基于Gtid，因事务号是唯一的，更改同步指向不需要知道binlog文件名和position位置点，固简化了在客户端部署agent做数据补齐。

3）无需安装，就两个文件，一个是（环境配置检查）可执行文件masterha_check_repl_mysql，一个是（故障自动转移auto failover和在线平滑切换switch）可执行文件masterha_manager_mysql

### 配置文件（请按照app1.cnf范例模板严丝合缝的去设置）

### 环境配置检查

###### shell> chmod 755 masterha_check_repl_mysql
###### shell> ./masterha_check_repl_mysql --conf=app1.cnf

### 开启守护进程，主库故障后，VIP自动故障转移，其他从库自动change master to 指向新主库
###### shell> chmod 755 masterha_manager_mysql
###### shell> ./masterha_manager_mysql --conf=app1.cnf start
