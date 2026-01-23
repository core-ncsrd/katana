#!/bin/bash
set -e

run_cmd() {
  CMD="$1"
  echo "Executing: $CMD"
  # Execute the command and capture exit code in a variable
  set +e
  OUTPUT=$(eval "$CMD" 2>&1)
  EXIT_CODE=$?
  set -e

  echo "$OUTPUT"

  if [ $EXIT_CODE -eq 0 ]; then
    echo "Success: Command executed successfully."
  else
    echo "Error: Command failed with exit code $EXIT_CODE."
    exit 1
  fi
  echo ""
}

run_cmd "sudo katana nfvo add -f osm.json"
run_cmd "sudo katana location add -f templates/example_config_files/location/example_group0_edge.json"
run_cmd "sudo katana function add -f templates/example_config_files/Functions/example_demo5gcore.json"
run_cmd "sudo katana function add -f templates/example_config_files/Functions/example_demo5ggnb.json"
run_cmd "sudo katana vim add -f vimEdge.json"
run_cmd "sudo katana vim add -f vimCore.json"
run_cmd "sudo katana slice add --pqc -f templates/example_config_files/nest/example_group0_nest_fw.json"

echo "All commands executed successfully."
