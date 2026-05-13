#!/bin/bash
# quic_tester.sh  —  same 5×5 matrix as tester.sh but using Python QUIC pair
#
# Start receiver first:
#   python3 receiver.py [--no-tls]
# Then run this script:
#   bash quic_tester.sh           # TLS on  (default)
#   bash quic_tester.sh --no-tls  # TLS off (connectivity testing)

SERVER="192.168.0.104"
PORT=5210
DURATION=15
TLS_FLAG="${1:-}"          # pass --no-tls as $1 to disable TLS

PARALLELS=(1 5 10 20 40)
BANDWIDTHS=("500M" "1G" "2G" "5G" "8G")

OUT="quic_results.csv"
echo "P,BW_target_Mbps,BW_actual_Mbps,CPU_avg,CPU_max_core" > "$OUT"

for P in "${PARALLELS[@]}"; do
  for BW in "${BANDWIDTHS[@]}"; do

    echo "Running QUIC test P=$P BW=$BW ${TLS_FLAG}"

    CPU_LOG="quic_cpu_${P}_${BW}.log"
    NET_LOG="quic_net_${P}_${BW}.log"

    mpstat -P ALL 1 > "$CPU_LOG" &
    MPSTAT_PID=$!

    sleep 2

    python3 sender.py \
      --server   "$SERVER" \
      --port     "$PORT"   \
      --duration "$DURATION" \
      --parallel "$P"      \
      --bandwidth "$BW"    \
      $TLS_FLAG > "$NET_LOG" 2>&1

    kill $MPSTAT_PID 2>/dev/null

    BW_ACTUAL=$(grep "Mbps" "$NET_LOG" | grep -oE '[0-9.]+ Mbps' | tail -1 | awk '{print $1}')

    if [[ -z "$BW_ACTUAL" ]]; then
      echo "  Test failed — dumping sender output:"
      cat "$NET_LOG"
      echo "  Skipping."
      continue
    fi

    CPU_AVG=$(awk '/all/ && $3 ~ /^[0-9.]+$/ {sum+=$3+$5; c++} END {if(c>0) print sum/c}' "$CPU_LOG")
    CPU_MAX=$(awk '$2 ~ /^[0-9]+$/ {val=$3+$5; if(val>max) max=val} END {print max}' "$CPU_LOG")

    if [[ "$BW" == *G ]]; then
      BW_TARGET=$(echo "${BW%G}*1000" | bc)
    else
      BW_TARGET=${BW%M}
    fi

    echo "$P,$BW_TARGET,$BW_ACTUAL,$CPU_AVG,$CPU_MAX" >> "$OUT"
    echo "  → actual=${BW_ACTUAL} Mbps  CPU_avg=${CPU_AVG}%  CPU_max_core=${CPU_MAX}%"

    sleep 3
  done
done

echo ""
echo "Done → $OUT"