FROM onap/policy-apex-pdp:2.6.0
WORKDIR /home/apexuser

COPY katana-apex/policy-apex/. ./policy-apex/
RUN mkdir -p ./policy-json
COPY katana-apex/policy-json/. ./policy-json/
COPY katana-apex/logic/. ./logic/
COPY katana-apex/config/. ./config/
COPY katana-apex/logs/logback.xml /opt/app/policy/apex-pdp/etc/
COPY katana-apex/tosca-template/. ./tosca-template/

COPY katana-apex/scripts/. ./

EXPOSE 12345 18989 23324 8080 5000 9092

RUN apexCLIToscaEditor.sh -c policy-apex/Policy.apex -ot policy-json/Policy.json -l ./test.log -ac config/config.json -t ./tosca-template/ToscaTemplate.json
CMD ["./start.sh"]

#CMD ["./startTest.sh"]
