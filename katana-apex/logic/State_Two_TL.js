var logger = executor.logger;
var time = new Date();

logger.info("##START## State_Two_TL");

var report = executor.inFields.get("report");
logger.info("~~report: " + report);

var alertAlbumSize = executor.getContextAlbum("Alerts_Album").size();
logger.info("~~Alert Album has: " + alertAlbumSize + " elements");

var alertAlbumData = executor.getContextAlbum("Alerts_Album").get(String(alertAlbumSize-1));
logger.info("~~Got alert message from context with this timestamp: " + alertAlbumData.timestamp);

var policyType = alertAlbumData.alertType;

var action = "restart_slice";
var slice_id = alertAlbumData.sliceId;
var ns_id = alertAlbumData.alertMessage.get("NS_ID");
var nsd_id = alertAlbumData.alertMessage.get("NSD_ID");
var restrictions = { "relocate_ns" : true };
var extra_actions = { "notify_NEAT": true };

var policy = {
        "action": action,
        "slice_id": slice_id,
        "ns_id": ns_id,
        "nsd_id": nsd_id,
        "restrictions": restrictions,
        "extra_actions": extra_actions
    };

executor.outFields.put("policyType", policyType);
executor.outFields.put("policy", policy);

logger.info("##END## State_Two_TL");

var returnValue = true;
returnValue;
