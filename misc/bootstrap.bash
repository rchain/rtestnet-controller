#!/bin/bash
# requires bash, curl, date

pkg_url_attr="http://metadata.google.internal/computeMetadata/v1/instance/attributes/rtestnet_node_package_url"
pkg_dir=/opt/rtestnet-node
log_file=/var/log/rtestnet-node/startup.log

set -o pipefail
ret=0

mkdir -p "$(dirname "$log_file")" || ret=$?
if [[ $ret -ne 0 ]]; then
	echo "Failed to create log directory $(dirname "$log_file"): $ret" >&2
	ret=0
else
	exec >>"$log_file" 2>&1 || ret=$?
	if [[ $ret -ne 0 ]]; then
		echo "Failed to redirect output to $log_file: $ret" >&2
		ret=0
	fi
fi

echo "$(date -Is) Setting up rtestnet-node"

pkg_url="$(curl -fLs -H Metadata-Flavor:Google $pkg_url_attr)" || ret=$?
if [[ $ret -ne 0 ]]; then
	echo "Failed to get package URL from $pkg_url_attr: $ret" >&2
	exit $ret
fi


if [[ -e "$pkg_dir.hash" ]]; then
	local_hash="$(cat $pkg_dir.hash)" || ret=$?
	if [[ $ret -ne 0 ]]; then
		echo "Failed to read $pkg_dir.hash: $ret" >&2
		ret=0
	fi
fi
remote_hash="$(curl -fLs "$pkg_url.hash" | head -1)" || ret=$?
if [[ $ret -ne 0 || -z "$remote_hash" ]]; then
	echo "Failed to get $pkg_url.hash: $ret" >&2
	ret=0
fi
if [[ -z "$remote_hash" || "$local_hash" != "$remote_hash" ]]; then
	rm -rf "$pkg_dir" || ret=$?
	if [[ $ret -ne 0 ]]; then
		echo "Failed to remove directory $pkg_dir: $ret" >&2
		ret=0
	fi
fi

if [[ ! -e "$pkg_dir" ]]; then
	mkdir -p "$pkg_dir" || ret=$?
	if [[ $ret -ne 0 ]]; then
		echo "Failed to create package directory $pkg_dir: $ret" >&2
		exit $ret
	fi
	curl -fLs "$pkg_url" | tar -zxf - -C "$pkg_dir" || ret=$?
	if [[ $ret -ne 0 ]]; then
		echo "Failed to download package from $pkg_url: $ret" >&2
		exit $ret
	fi
	if [[ -n "$remote_hash" ]]; then
		echo -n "$remote_hash" >"$pkg_dir.hash" || ret=$?
		if [[ $ret -ne 0 ]]; then
			echo "Failed to write package hash to $pkg_dir.hash" >&2
			ret=0
		fi
	fi
fi

cd "$pkg_dir" || ret=$?
if [[ $ret -ne 0 ]]; then
	echo "Failed to change directory to $pkg_dir: $ret" >&2
	exit $ret
fi
if [[ ! -x setup ]]; then
	echo "No such executable file: $pkg_dir/setup" >&2
	exit 1
fi
nohup ./setup >>"$log_file" 2>&1 &
