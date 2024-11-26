#!/bin/sh

# Add the Katana Version on swagger.json
sed -i "s?katana.version?${KATANA_VERSION}?" "/my_swagger/swagger.json"
