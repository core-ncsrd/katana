#!/bin/sh

# Add the Katana Host IP Address on swagger.json
sed -i "s?katana.host?${KATANA_HOST}?" "/my_swagger/swagger.json"
