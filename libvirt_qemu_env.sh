cp /etc/init.d/libvirtd /etc/init.d/libvirtd.bak

function bakup()
{
	echo 'bakup', $1;
	mv $1 $1.bak
}

function replace_ln()
{
	echo  'replace: ', $1, 'will replace', $2;
	if [ -L	$2 ]
	then
		echo $2, 'is a symbolic link, ...error';
		exit;
	fi

	bakup $2;
	ln -s $1 $2;
}

sed -i s#PIDFILE=/var/#PIDFILE=/usr/local/var/#g /etc/init.d/libvirtd

#replace_ln /usr/local/etc/rc.d/init.d/libvirtd /etc/init.d/libvirtd

replace_ln /usr/local/bin/virsh /usr/bin/virsh
replace_ln /usr/local/sbin/libvirtd /usr/sbin/libvirtd


replace_ln /usr/local/bin/qemu-system-x86_64 /usr/libexec/qemu-kvm
replace_ln /usr/local/bin/qemu-img /usr/bin/qemu-img

echo '...ok'
