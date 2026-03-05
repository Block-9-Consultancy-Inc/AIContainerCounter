v4l2-ctl -d $1 --set-ctrl white_balance_automatic=0
v4l2-ctl -d $1 --set-ctrl white_balance_temperature=$2