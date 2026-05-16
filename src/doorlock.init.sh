#!/bin/sh

### BEGIN INIT INFO
# Provides:          doorlock
# Required-Start:    $remote_fs $syslog
# Required-Stop:     $remote_fs $syslog
# Default-Start:     2 3 4 5
# Default-Stop:      0 1 6
# Short-Description: Doorlock function using rpi camera
# Description:       Doorlock
### END INIT INFO

DEFAULTS="/etc/default/doorlock"
DOORLOCK_REPO_DIR="/home/pi/Facial-Recognition-Door-Lock"
DOORLOCK_APP_DIR="$DOORLOCK_REPO_DIR/src"
DOORLOCK_PYTHON_BIN="$DOORLOCK_REPO_DIR/.venv/bin/python"
DOORLOCK_PORT="8080"
DOORLOCK_CAMERA_BACKEND="auto"
DOORLOCK_CAMERA_INDEX="0"
DOORLOCK_CAMERA_DEVICE=""
DOORLOCK_CAMERA_WIDTH="1280"
DOORLOCK_CAMERA_HEIGHT="720"
DOORLOCK_CAMERA_FOURCC="MJPG"
DOORLOCK_PROCESSING_SCALE="0.5"
DOORLOCK_STREAM_SCALE="1.0"
PIDFILE="/var/run/doorlock.pid"
LOGFILE="/var/log/doorlock.log"

if [ -r "$DEFAULTS" ]; then
	set -a
	. "$DEFAULTS"
	set +a
fi

case "$1" in
	start)
		echo "Starting doorlock"

		if [ ! -x "$DOORLOCK_PYTHON_BIN" ]; then
			echo "Python not found: $DOORLOCK_PYTHON_BIN"
			exit 1
		fi

		if [ ! -d "$DOORLOCK_APP_DIR" ]; then
			echo "Application directory not found: $DOORLOCK_APP_DIR"
			exit 1
		fi

		if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
			echo "Doorlock is already running"
			exit 0
		fi

		cd "$DOORLOCK_APP_DIR" || exit 1
		export DOORLOCK_REPO_DIR DOORLOCK_APP_DIR DOORLOCK_PYTHON_BIN DOORLOCK_PORT
		export DOORLOCK_CAMERA_BACKEND DOORLOCK_CAMERA_INDEX DOORLOCK_CAMERA_DEVICE
		export DOORLOCK_CAMERA_WIDTH DOORLOCK_CAMERA_HEIGHT DOORLOCK_CAMERA_FOURCC
		export DOORLOCK_PROCESSING_SCALE DOORLOCK_STREAM_SCALE
		"$DOORLOCK_PYTHON_BIN" ./doorlock.py >> "$LOGFILE" 2>&1 &
		echo $! > "$PIDFILE"

		sleep 2
		if ! kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
			echo "Doorlock failed to start. Last log lines:"
			tail -n 80 "$LOGFILE"
			rm -f "$PIDFILE"
			exit 1
		fi
		;;

	stop)
		echo "Stopping doorlock"

		if [ -f "$PIDFILE" ]; then
			PID="$(cat "$PIDFILE")"
			if kill -0 "$PID" 2>/dev/null; then
				kill "$PID"
				for _ in 1 2 3 4 5 6 7 8 9 10; do
					if ! kill -0 "$PID" 2>/dev/null; then
						break
					fi
					sleep 1
				done
				if kill -0 "$PID" 2>/dev/null; then
					echo "Doorlock did not stop cleanly, killing $PID"
					kill -9 "$PID"
				fi
			fi
			rm -f "$PIDFILE"
		else
			pkill -f "$DOORLOCK_PYTHON_BIN ./doorlock.py" 2>/dev/null || true
		fi
		;;

	restart)
		"$0" stop
		sleep 1
		"$0" start
		;;

	status)
		if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
			echo "Doorlock is running"
			exit 0
		fi

		echo "Doorlock is not running"
		exit 3
		;;

	*)
		echo "Usage: /etc/init.d/doorlock {start|stop|restart|status}"
		exit 1
		;;
esac

exit 0
