var logger = executor.logger;

logger.info("##START## SM_ALERT_POLICY_SSL");

logger.info("Possible Outputs: " + executor.stateOutputNames);

var alertAlbum = executor.getContextAlbum("Alerts_Album");
var alertAlbumSize = alertAlbum.size();

var lastAlertData = alertAlbum.get(String(alertAlbumSize-1));
logger.info("~~Last Alert" + lastAlertData);

var lastAlertSliceId = lastAlertData.sliceId;
logger.info("~~Last Alert is on slice" + lastAlertData.sliceId);

var alertInstance = 0;
for (var i = 0; i < alertAlbum.size(); i++) {
	logger.info("~~Check if : " +alertAlbum.get(String(i)).sliceId + " equals " + lastAlertData.sliceId);
	if(alertAlbum.get(String(i)).sliceId == lastAlertData.sliceId)
	{
		alertInstance++;
		logger.info("~~Alert has been matched");

	}
}

logger.info("~~Number of alertInstance: " + alertInstance);

if(alertInstance === 1)
{
	//step 1 First Occurance
	executor.setSelectedStateOutputName("firstCase");

}
else if(alertInstance === 2)
{
	//step 2, Happened before
	executor.setSelectedStateOutputName("secondCase");

}
else if(alertInstance > 2)
{
	//step 3, report fault
	executor.setSelectedStateOutputName("thirdCase");

}

logger.info("Selected Output: " + executor.selectedStateOutputName);

logger.info("##END## SM_ALERT_POLICY_SSL");

var returnValue = true;
returnValue;