---
name: ansible
description: "Automation & configuration management Ansible. Trigger: /ansible"
---

# Ansible Automation

## Ad-hoc Commands
```bash
ansible all -m ping
ansible all -m shell -a "uptime"
ansible webservers -m yum -a "name=nginx state=present" --become
ansible all -m copy -a "src=file.txt dest=/tmp/file.txt"
ansible all -m service -a "name=nginx state=started" --become
```

## Playbook
```yaml
---
- hosts: webservers
  become: yes
  vars:
    http_port: 80
    app_version: "1.0"
  
  tasks:
    - name: Install nginx
      yum:
        name: nginx
        state: present
      when: ansible_os_family == "RedHat"
    
    - name: Start nginx
      service:
        name: nginx
        state: started
        enabled: yes
    
    - name: Copy config
      template:
        src: nginx.conf.j2
        dest: /etc/nginx/nginx.conf
      notify: restart nginx
    
    - name: Ensure directory exists
      file:
        path: /var/www/html
        state: directory
        owner: www-data
        mode: '0755'
  
  handlers:
    - name: restart nginx
      service:
        name: nginx
        state: restarted
```

```bash
ansible-playbook site.yml
ansible-playbook site.yml --limit webservers
ansible-playbook site.yml --tags "install"
ansible-playbook site.yml --check          # dry run
ansible-playbook site.yml --diff           # show changes
ansible-playbook site.yml -e "version=2.0"
```

## Roles
```
roles/
  common/
    tasks/
      main.yml
    handlers/
      main.yml
    templates/
      config.j2
    files/
    vars/
      main.yml
    defaults/
      main.yml
    meta/
      main.yml
```

```yaml
- hosts: all
  roles:
    - common
    - role: nginx
      vars:
        nginx_port: 80
```

## Inventory
```ini
# hosts.ini
[webservers]
web1 ansible_host=192.168.1.10
web2 ansible_host=192.168.1.11

[dbservers]
db1 ansible_host=192.168.1.20

[production:children]
webservers
dbservers

[all:vars]
ansible_user=deploy
ansible_ssh_private_key_file=~/.ssh/id_rsa
```

```yaml
# hosts.yml
all:
  children:
    webservers:
      hosts:
        web1:
          ansible_host: 192.168.1.10
        web2:
          ansible_host: 192.168.1.11
    dbservers:
      hosts:
        db1:
          ansible_host: 192.168.1.20
```

## Vault
```bash
ansible-vault create secrets.yml
ansible-vault edit secrets.yml
ansible-vault encrypt existing.yml
ansible-vault decrypt secrets.yml
ansible-vault view secrets.yml
ansible-playbook site.yml --ask-vault-pass
ansible-playbook site.yml --vault-password-file=.vault_pass
```

## Galaxy
```bash
ansible-galaxy init myrole
ansible-galaxy install geerlingguy.docker
ansible-galaxy collection install community.general
ansible-galaxy role list
ansible-galaxy collection list
```

## Troubleshooting
| Masalah | Solusi |
|---------|--------|
| Connection timeout | Cek SSH, firewall, inventory |
| Module error | Cek syntax, `--check`, `--diff` |
| Permission denied | `--become`, cek sudoers |
| Variable undefined | Cek vars, defaults |
| Task failed | `ansible-playbook -v`, cek logs |
