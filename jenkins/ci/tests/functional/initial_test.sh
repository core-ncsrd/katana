#!/bin/bash

# *** Initial Test ***

echo """
# *********************************
# **** Katana Integration Test ****
# *********************************
"""

# Get the katana logs to check if the 
response=$(docker container run --rm --network container:katana-nbi nicolaka/netshoot curl --write-out '%{http_code}' --silent --output /dev/null http://katana-nbi:8000/api/slice)

if [[ $response != 200 ]]; then
echo "**** TEST FAILED ****"
echo "**** RESPONSE = $response *****"
exit 1
fi

echo "**** TEST PASSED ****"