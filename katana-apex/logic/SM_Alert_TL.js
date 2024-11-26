var logger = executor.logger;
var time = new Date();

logger.info("##START## SM_Alert_TL");

var sliceId = executor.inFields.get("sliceId");
logger.info("~~sliceId: " + sliceId);

var alertType = executor.inFields.get("alertType");
logger.info("~~alertType: " + alertType);

var alertMessage = executor.inFields.get("alertMessage");
logger.info("~~alertMessage: " + alertMessage);

var timestamp = time;
logger.info("~~timestamp: " + timestamp);

var contextAlert = {"sliceId":sliceId, "alertType":alertType, "alertMessage":alertMessage, "timestamp":timestamp};

var alertAlbumSize = executor.getContextAlbum("Alerts_Album").size();
logger.info("~~Alert Album has: " + alertAlbumSize + " elements");

executor.getContextAlbum("Alerts_Album").put(String(alertAlbumSize), contextAlert);
logger.info("~~Alert Message stored in location: " + alertAlbumSize + " in Context_Album");

var contextAlbumValues = executor.getContextAlbum("Alerts_Album").values();
logger.info("~~Alerts Album Data: " + contextAlbumValues);

var contextAlbumKeys = executor.getContextAlbum("Alerts_Album").keySet();
logger.info("~~Alerts Album Keys: " + contextAlbumKeys);

var alertAlbumData = executor.getContextAlbum("Alerts_Album").get(String(alertAlbumSize));
logger.info("~~Got alert message from context with this timestamp: " + alertAlbumData.timestamp);

executor.outFields.put("report", "Alert is stored");

logger.info("##END## SM_Alert_TL");

var returnValue = true;
returnValue;
