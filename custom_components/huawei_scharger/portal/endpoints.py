"""URL paths, object class ids and signal ids of the FusionSolar web portal.

The values correspond to the requests the portal's own charger page issues.
The API is unofficial and may change without notice.
"""

DEFAULT_HOST = "eu5.fusionsolar.huawei.com"
HOST_SUFFIX = ".fusionsolar.huawei.com"

# --- login / session ---------------------------------------------------------
PATH_PUBKEY = "/unisso/pubkey"
PATH_LOGIN_PAGE = "/unisso/login.action"
PATH_VALIDATE_USER = "/unisso/v3/validateUser.action"
PATH_VALIDATE_USER_LA5 = "/rest/dp/uidm/unisso/v1/validate-user"
PATH_FINAL_AUTH_LA5 = "/rest/pvms/web/login/v1/redirecturl?isFirst=false"
PATH_LOGIN_CUSTOMIZE = "/pvmswebsite/loginCustomize.html"
PATH_KEEP_ALIVE = "/rest/dpcloud/auth/v1/keep-alive"
PATH_APP_PAGE = "/uniportal/pvmswebsite/assets/build/cloud.html"
PATH_STATION_LIST = "/rest/pvms/web/station/v1/station/station-list"

# --- wallbox -----------------------------------------------------------------
PATH_DEVICE_TREE = "/rest/dp/pvms/organization/v1/tree"
PATH_LIVE_VALUES = "/rest/neteco/web/homemgr/v1/device/get-realtime-info"
PATH_READ_SETTINGS = "/rest/pvms/web/device/v1/deviceExt/get-config-signals"
PATH_WRITE_SETTINGS = "/rest/pvms/web/device/v1/deviceExt/set-config-signals"
PATH_DEVICE_SIGNALS = "/rest/pvms/web/device/v1/device-realtime-data"

MOC_WALLBOX = 60080
MOC_CONNECTOR = 60081

# live values of the charging connector
SIGNAL_POWER_KW = 10013
SIGNAL_WORKING_STATUS = 10004
SIGNAL_WORKING_MODE = 2101764
SIGNAL_PHASE_CURRENTS = {"l1": 10032, "l2": 10034, "l3": 10033}

# live values of the wallbox itself
SIGNAL_ENERGY_TOTAL_KWH = 10008
SIGNAL_FIRMWARE = 10001
SIGNAL_MODEL = 10007
SIGNAL_SERIAL = 2101252
SIGNAL_TEMPERATURE = 2101271

SIGNAL_LOCK_STATE = 10023          # connector, "Locked" / "Unlocked"
SIGNAL_REPORTED_STATUS = 2101763   # connector

# settings ("config signals"); the portal tells which device owns a signal
SETTING_DYNAMIC_POWER = 20001      # dynamic power limit (kW), writable
SETTING_MAX_POWER = 538976598      # rated maximum power (kW), read only
SETTING_MODE = 20002               # working mode, writable
SETTING_MAX_CURRENT = 20003        # max charging current (A), writable
SETTING_PHASE_SWITCHING = 20004    # automatic phase switching 0/1, writable
SETTING_LOCK_MODE = 20005          # connector locking mode, writable
SETTING_GRID_SHARE_PV = 20006      # max grid power in PV mode (kW), writable
SETTING_SURPLUS_START = 20007      # surplus power needed to start (kW), writable
SETTING_DYNAMIC_ENABLED = 538976529  # dynamic charge power on/off 0/1, writable

# values of SETTING_MODE
MODE_CODES = {"normal": "0", "pv_preferred": "1"}
MODE_NAMES = {code: name for name, code in MODE_CODES.items()}

# values of SETTING_LOCK_MODE
LOCK_MODE_CODES = {"always": "0", "while_charging": "1", "after_plug_in": "2"}
LOCK_MODE_NAMES = {code: name for name, code in LOCK_MODE_CODES.items()}

# plant level
PATH_SOCIAL_CONTRIBUTION = "/rest/pvms/web/station/v1/station/social-contribution"

# power above which the connector counts as "charging" (kW)
CHARGING_THRESHOLD_KW = 0.3
