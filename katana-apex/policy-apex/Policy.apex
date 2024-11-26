
#----------------------------------------------------------------------------------------------------------------------------------------------------------------

model create name=5GENESIS_ATHENS_POLICY_MODEL

#----------------------------------------------------------------------------------------------------------------------------------------------------------------

##-- Primitive Types --##

schema create		name=String_Type			flavour=Java		schema=java.lang.String
schema create 		name=Object_Type			flavour=Java		schema=java.lang.Object

#----------------------------------------------------------------------------------------------------------------------------------------------------------------

##-- Events --##

event create 				name=SMAlert			nameSpace=sm.alert.manager.events	source="SMAlertManager"		target="APEX"
event parameter create 		name=SMAlert			parName=sliceId			schemaName=String_Type
event parameter create 		name=SMAlert			parName=alertType			schemaName=String_Type
event parameter create 		name=SMAlert			parName=alertMessage			schemaName=Object_Type

event create 				name=SMAlertOutput			nameSpace=sm.alert.manager.events	source="APEX"		target="SM"
event parameter create 		name=SMAlertOutput			parName=report			schemaName=String_Type

event create 				name=APEX_Wrapped_Event			nameSpace=sm.alert.manager.events	source="APEX"		target="SM"
event parameter create 		name=APEX_Wrapped_Event			parName=policyType			schemaName=String_Type
event parameter create 		name=APEX_Wrapped_Event			parName=policy			schemaName=Object_Type

#----------------------------------------------------------------------------------------------------------------------------------------------------------------

##-- Albums --##

album create				name=Alerts_Album					scope=GLOBAL			writable=true		schemaName=Object_Type

#----------------------------------------------------------------------------------------------------------------------------------------------------------------

##-- TASKS --##

task create					name=SM_Alert_Task
task inputfield create		name=SM_Alert_Task				fieldName=sliceId					schemaName=String_Type
task inputfield create		name=SM_Alert_Task				fieldName=alertType					schemaName=String_Type
task inputfield create		name=SM_Alert_Task				fieldName=alertMessage					schemaName=Object_Type
task outputfield create		name=SM_Alert_Task				fieldName=report				schemaName=String_Type
task contextref create		name=SM_Alert_Task				albumName=Alerts_Album
task logic create			name=SM_Alert_Task				logicFlavour=JAVASCRIPT					logic=LS
#MACROFILE:"logic/SM_Alert_TL.js"
LE

task create					name=State_One_Task
task inputfield create		name=State_One_Task				fieldName=report					schemaName=String_Type
task outputfield create		name=State_One_Task				fieldName=report					schemaName=String_Type
task contextref create		name=State_One_Task				albumName=Alerts_Album
task logic create			name=State_One_Task				logicFlavour=JAVASCRIPT					logic=LS
#MACROFILE:"logic/State_One_TL.js"
LE

task create					name=State_Two_Task
task inputfield create		name=State_Two_Task				fieldName=report					schemaName=String_Type
task outputfield create		name=State_Two_Task				fieldName=report					schemaName=String_Type
task contextref create		name=State_Two_Task				albumName=Alerts_Album
task logic create			name=State_Two_Task				logicFlavour=JAVASCRIPT					logic=LS
#MACROFILE:"logic/State_Two_TL.js"
LE

task create					name=State_Three_Task
task inputfield create		name=State_Three_Task			fieldName=report					schemaName=String_Type
task outputfield create		name=State_Three_Task			fieldName=report					schemaName=String_Type
task contextref create		name=State_Three_Task			albumName=Alerts_Album
task logic create			name=State_Three_Task			logicFlavour=JAVASCRIPT					logic=LS
#MACROFILE:"logic/State_Three_TL.js"
LE

#----------------------------------------------------------------------------------------------------------------------------------------------------------------

##-- POLICIES --##

policy create							name=SM_Alert_Policy		template=FREEFORM				firstState=Trigger_State

policy state create						name=SM_Alert_Policy		stateName=State_One				triggerName=SMAlertOutput				defaultTaskName=State_One_Task
policy state output	create				name=SM_Alert_Policy		stateName=State_One				outputName=stateOne 					eventName=APEX_Wrapped_Event
policy state taskref create				name=SM_Alert_Policy		stateName=State_One				taskName=State_One_Task					outputType=DIRECT				outputName=stateOne

policy state create						name=SM_Alert_Policy		stateName=State_Two				triggerName=SMAlertOutput				defaultTaskName=State_Two_Task
policy state output	create				name=SM_Alert_Policy		stateName=State_Two				outputName=stateTwo 					eventName=APEX_Wrapped_Event
policy state taskref create				name=SM_Alert_Policy		stateName=State_Two				taskName=State_Two_Task					outputType=DIRECT				outputName=stateTwo

policy state create						name=SM_Alert_Policy		stateName=State_Three			triggerName=SMAlertOutput				defaultTaskName=State_Three_Task
policy state output	create				name=SM_Alert_Policy		stateName=State_Three			outputName=stateThree 					eventName=APEX_Wrapped_Event
policy state taskref create				name=SM_Alert_Policy		stateName=State_Three			taskName=State_Three_Task				outputType=DIRECT				outputName=stateThree

policy state create						name=SM_Alert_Policy		stateName=Trigger_State			triggerName=SMAlert						defaultTaskName=SM_Alert_Task
policy state output	create				name=SM_Alert_Policy		stateName=Trigger_State			outputName=firstCase 					eventName=SMAlertOutput			nextState=State_One
policy state output	create				name=SM_Alert_Policy		stateName=Trigger_State			outputName=secondCase 					eventName=SMAlertOutput			nextState=State_Two
policy state output	create				name=SM_Alert_Policy		stateName=Trigger_State			outputName=thirdCase 					eventName=SMAlertOutput			nextState=State_Three
policy state contextref create			name=SM_Alert_Policy		stateName=Trigger_State			albumName=Alerts_Album

policy state finalizerlogic create		name=SM_Alert_Policy  		stateName=Trigger_State 		finalizerLogicName=Finalizer_Logic 		logicFlavour=JAVASCRIPT logic=LS
#MACROFILE:"logic/SM_Alert_Policy_SSL.js"
LE
policy state taskref create				name=SM_Alert_Policy		stateName=Trigger_State			taskName=SM_Alert_Task		outputType=LOGIC					outputName=Finalizer_Logic

#-------------------------------------------------------------------------------------------------------------------------------------------------
