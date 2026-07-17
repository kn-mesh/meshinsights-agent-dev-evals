**Credentials are stored in the .env file:**
- mongodb_username=...
- mongodb_password=...
- mongodb_host=...
- mongo_database=...

## Which sensor ID should we use?

Use the customer-provided Pulse sensor number as the primary lookup key.

- Example customer sensor ID: `250003575`
- In Mongo this maps to `sensorIdDec` (integer)
- In `sensordevices` the same value may also appear as `deviceId` (string), but `sensorIdDec` is the better canonical key because it is present in both alarms and telemetry
- `sensorId` is a different string identifier (example format: `feffff000ee6c077`); it is useful as a cross-check, but it is not the best starting key for cross-collection queries

### Short answer on `_id`

No, Mongo `_id` is not the main ID you should start with when the customer gives you a sensor number like `250003575`.

- `alarms._id` identifies one alarm record
- `sensordatas._id` identifies one telemetry record
- `sensordevices._id` identifies one device document
- `steamtrapdevices._id` identifies one install/metadata document

Those `_id` values are row identifiers, not the durable customer-facing sensor key.

## Verified join path for querying Pulse data

Validated against the live database on 2026-03-19 using sensor `250003575`.

### 1. Start from the customer sensor number

```javascript
const sensorIdDec = 250003575;
```

### 2. Query alarms directly by `sensorIdDec`

```javascript
db.alarms.find({ sensorIdDec });
```

### 3. Query telemetry directly by `metadata.sensorIdDec`

```javascript
db.sensordatas.find({ "metadata.sensorIdDec": sensorIdDec });
```

### 4. Query install / asset metadata through `sensordevices`

First find the matching `sensordevices` rows:

```javascript
db.sensordevices.find({ sensorIdDec });
```

Then take the `sensordevices.sensor` ObjectId and use that to query `steamtrapdevices`:

```javascript
const device = db.sensordevices.findOne({ sensorIdDec });
db.steamtrapdevices.find({ sensor: device.sensor });
```

### Important: `steamtrapdevices.sensor` joins to `sensordevices.sensor`, not `sensordevices._id`

This matters a lot for query writing.

- For sample sensor `250003575`, `steamtrapdevices.sensor = sensordevices.sensor` returned the expected install metadata
- `steamtrapdevices.sensor = sensordevices._id` returned no matches
- A broader check across the database showed `0` overlaps between `steamtrapdevices.sensor` and `sensordevices._id`
- The same broader check showed `12,713` overlaps between `steamtrapdevices.sensor` and `sensordevices.sensor`

## Recommended query flow

When the customer gives a sensor number such as `250003575`, use this flow:

1. Use `sensorIdDec = 250003575`
2. Pull alarms from `alarms.sensorIdDec`
3. Pull telemetry from `sensordatas.metadata.sensorIdDec`
4. Pull `sensordevices` rows for `sensorIdDec`
5. For each `sensordevices` row, use its `sensor` ObjectId to retrieve the matching `steamtrapdevices` metadata row

## Re-installation / historical metadata caveat

The same `sensorIdDec` can appear in more than one `sensordevices` row over time.

For example, sensor `250003575` had:

- an older deleted/offline `sensordevices` row linked to one `steamtrapdevices` install record
- a newer working `sensordevices` row linked to a different `steamtrapdevices` install record

This means:

- `sensorIdDec` is the right durable key for alarms and telemetry
- installation metadata is time-dependent
- if you need the current install, filter `sensordevices` to the active row (`isDeleted != true`, newest `lastUpdatedAt`)
- if you need the install that was active when an alarm fired, match the alarm timestamp against the install/remove window on the relevant `sensordevices` / `steamtrapdevices` records

## Practical starter queries

### Current alarms for one sensor

```javascript
db.alarms
  .find({ sensorIdDec: 250003575 })
  .sort({ detectedAt: -1 });
```

### Recent telemetry for one sensor

```javascript
db.sensordatas
  .find({ "metadata.sensorIdDec": 250003575 })
  .sort({ createdAt: -1 });
```

### Current install metadata for one sensor

```javascript
const device = db.sensordevices
  .find({ sensorIdDec: 250003575, isDeleted: { $ne: true } })
  .sort({ lastUpdatedAt: -1 })
  .limit(1)
  .toArray()[0];

db.steamtrapdevices.find({ sensor: device.sensor });
```

**Relevant Collections in the database:**
*Data schemas in Standard JSON format*

### read@dashboardv2.sensordatas
*Telemetry data from sensor kits*
**Definitely Relevant fields:**
- condensationTemperature = Condensation Side Temperature
- pipeTemperature = Steam Side Temperature
- frontMic
- metadata.sensorIdDec = primary sensor lookup key for telemetry queries
- metadata.sensorId = alternate string sensor identifier
- _id

**Maybe Relevant fields:**
- internalTemperature
- rearMic (not used by the SMEs in their dashboard)
- PCBTemp
- errorCode

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": [
    "_id",
    "createdAt",
    "gatewayId",
    "metadata",
    "processedAt"
  ],
  "properties": {
    "_id": {
      "$ref": "#/$defs/ObjectId"
    },
    "chipTemp": {
      "$ref": "#/$defs/Double"
    },
    "condensationTemperature": {
      "anyOf": [
        {
          "$ref": "#/$defs/Double"
        },
        {
          "type": "integer"
        }
      ]
    },
    "createdAt": {
      "$ref": "#/$defs/Date"
    },
    "errorCode": {
      "type": "integer"
    },
    "fFrequency": {
      "type": "integer"
    },
    "frontFrequency": {
      "type": "integer"
    },
    "frontMic": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "$ref": "#/$defs/Double"
        }
      ]
    },
    "gatewayId": {
      "type": [
        "string",
        "integer"
      ]
    },
    "internalTemperature": {
      "anyOf": [
        {
          "$ref": "#/$defs/Double"
        },
        {
          "type": "integer"
        }
      ]
    },
    "metadata": {
      "type": "object",
      "required": [
        "sensorId",
        "sensorIdDec"
      ],
      "properties": {
        "sensorId": {
          "type": "string"
        },
        "sensorIdDec": {
          "type": "integer"
        }
      }
    },
    "PCBTemp": {
      "$ref": "#/$defs/Double"
    },
    "pcbTemperature": {
      "$ref": "#/$defs/Double"
    },
    "pipeTemperature": {
      "anyOf": [
        {
          "$ref": "#/$defs/Double"
        },
        {
          "type": "integer"
        }
      ]
    },
    "processedAt": {
      "$ref": "#/$defs/Date"
    },
    "rearMic": {
      "anyOf": [
        {
          "$ref": "#/$defs/Double"
        },
        {
          "type": "integer"
        }
      ]
    },
    "rssi": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "$ref": "#/$defs/Double"
        }
      ]
    },
    "snr": {
      "anyOf": [
        {
          "$ref": "#/$defs/Double"
        },
        {
          "type": "integer"
        }
      ]
    },
    "voltageBattery": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "$ref": "#/$defs/Double"
        }
      ]
    }
  },
  "$defs": {
    "ObjectId": {
      "type": "object",
      "properties": {
        "$oid": {
          "type": "string",
          "pattern": "^[0-9a-fA-F]{24}$"
        }
      },
      "required": [
        "$oid"
      ],
      "additionalProperties": false
    },
    "Double": {
      "oneOf": [
        {
          "type": "number"
        },
        {
          "type": "object",
          "properties": {
            "$numberDouble": {
              "enum": [
                "Infinity",
                "-Infinity",
                "NaN"
              ]
            }
          }
        }
      ]
    },
    "Date": {
      "type": "object",
      "properties": {
        "$date": {
          "type": "string",
          "format": "date-time"
        }
      },
      "required": [
        "$date"
      ],
      "additionalProperties": false
    }
  }
}

```

### read@dashboardv2.steamtrapdevices
*Metadata at install*
**Definitely Relevant fields:**
- sensor = joins to `sensordevices.sensor`
- _id
- installedAt
- type (steam trap type: "float", "inverted bucket" )



***Maybe Relevant fields:**
- removedAt
- auditAtInstall
- tag (installer sets a tag # for a given site which can help identify other steam traps at the same site which may be nearby)
- modelNumber (steam trap model number??)
- steamPressure (what exactly is this?)
- steamTemperature (what exactly is this?)
- manufacturer (steam trap manufacturer)
- processEquipment (process installed in "Drip", "Laundry Rollers"...high variability of naming since it's a free text field)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": [
    "_id",
    "__v",
    "cost",
    "equipmentLocation",
    "insidePipeDiameter",
    "manufacturer",
    "modelNumber",
    "processEquipment",
    "sensor",
    "steamPressure",
    "steamTemperature",
    "tag",
    "type"
  ],
  "properties": {
    "_id": {
      "$ref": "#/$defs/ObjectId"
    },
    "__v": {
      "type": "integer"
    },
    "auditAtInstall": {
      "type": "string"
    },
    "condensateTemperature": {
      "type": [
        "string",
        "integer"
      ]
    },
    "cost": {
      "type": [
        "string",
        "null"
      ]
    },
    "equipmentLocation": {
      "type": [
        "string",
        "null"
      ]
    },
    "insidePipeDiameter": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        },
        {
          "$ref": "#/$defs/Double"
        },
        {
          "type": "integer"
        }
      ]
    },
    "insidePipeDiameterSize": {
      "anyOf": [
        {
          "$ref": "#/$defs/Double"
        },
        {
          "type": "integer"
        }
      ]
    },
    "installedAt": {
      "anyOf": [
        {
          "$ref": "#/$defs/Date"
        },
        {
          "type": "string"
        }
      ]
    },
    "isDeleted": {
      "type": "boolean"
    },
    "manufacturer": {
      "type": [
        "string",
        "null"
      ]
    },
    "modelNumber": {
      "type": [
        "string",
        "null",
        "integer"
      ]
    },
    "outsidePipeDiameter": {
      "type": [
        "string",
        "integer"
      ]
    },
    "processEquipment": {
      "type": [
        "string",
        "null"
      ]
    },
    "removedAt": {
      "$ref": "#/$defs/Date"
    },
    "sensor": {
      "$ref": "#/$defs/ObjectId"
    },
    "steamPressure": {
      "type": [
        "string",
        "null",
        "integer"
      ]
    },
    "steamTemperature": {
      "type": [
        "string",
        "null",
        "integer"
      ]
    },
    "tag": {
      "type": [
        "string",
        "null",
        "integer"
      ]
    },
    "type": {
      "type": [
        "string",
        "null"
      ]
    }
  },
  "$defs": {
    "ObjectId": {
      "type": "object",
      "properties": {
        "$oid": {
          "type": "string",
          "pattern": "^[0-9a-fA-F]{24}$"
        }
      },
      "required": [
        "$oid"
      ],
      "additionalProperties": false
    },
    "Double": {
      "oneOf": [
        {
          "type": "number"
        },
        {
          "type": "object",
          "properties": {
            "$numberDouble": {
              "enum": [
                "Infinity",
                "-Infinity",
                "NaN"
              ]
            }
          }
        }
      ]
    },
    "Date": {
      "type": "object",
      "properties": {
        "$date": {
          "type": "string",
          "format": "date-time"
        }
      },
      "required": [
        "$date"
      ],
      "additionalProperties": false
    }
  }
}
```




### read@dashboardv2.sensordevices
*Device registry / bridge collection between customer sensor IDs and install metadata*
**Potential Relevant fields:**
- _id
- sensor = ObjectId used to join into `steamtrapdevices.sensor`
- deviceId
- sensorIdDec = customer-facing numeric sensor ID
- sensorId = alternate string sensor ID
- isFaulty
- isReverseInstalled
- status ("Offline", "Working", "Failed Open")

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": [
    "_id",
    "firmwareVersion"
  ],
  "properties": {
    "_id": {
      "$ref": "#/$defs/ObjectId"
    },
    "__v": {
      "type": "integer"
    },
    "deviceId": {
      "type": [
        "string",
        "null"
      ]
    },
    "firmwareVersion": {
      "type": "string"
    },
    "gatewayId": {
      "type": [
        "string",
        "integer"
      ]
    },
    "history": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "hwDeviceInfo": {
      "type": "object",
      "required": [],
      "properties": {
        "appEUI": {
          "type": "string"
        },
        "appKey": {
          "type": "string"
        },
        "buildDate": {
          "$ref": "#/$defs/Date"
        },
        "deviceProfile": {
          "$ref": "#/$defs/ObjectId"
        },
        "hardwareVersion": {
          "type": "string"
        },
        "LNS": {
          "type": "string"
        },
        "lorawanSpecVer": {
          "type": "string"
        },
        "OpsAssetId": {
          "type": "string"
        },
        "softwareVersion": {
          "type": "string"
        }
      }
    },
    "installedAt": {
      "anyOf": [
        {
          "$ref": "#/$defs/Date"
        },
        {
          "type": "null"
        }
      ]
    },
    "isDeleted": {
      "type": "boolean"
    },
    "isFaulty": {
      "type": "boolean"
    },
    "isReverseInstalled": {
      "type": "boolean"
    },
    "lastUpdatedAt": {
      "$ref": "#/$defs/Date"
    },
    "onWatchList": {
      "$ref": "#/$defs/Date"
    },
    "productionTestResult": {
      "type": "object",
      "required": [
        "isCopied"
      ],
      "properties": {
        "condensateTemp": {
          "$ref": "#/$defs/Double"
        },
        "cpuTemp": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "$ref": "#/$defs/Double"
            }
          ]
        },
        "frequency": {
          "anyOf": [
            {
              "$ref": "#/$defs/Double"
            },
            {
              "type": "null"
            }
          ]
        },
        "isCopied": {
          "type": "boolean"
        },
        "magnitude": {
          "type": "integer"
        },
        "pcbTemp": {
          "type": [
            "string",
            "null"
          ]
        },
        "steamTemp": {
          "$ref": "#/$defs/Double"
        },
        "vccVoltage": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "$ref": "#/$defs/Double"
            }
          ]
        }
      }
    },
    "removedAt": {
      "$ref": "#/$defs/Date"
    },
    "removedBy": {
      "$ref": "#/$defs/ObjectId"
    },
    "rssi": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "$ref": "#/$defs/Double"
        }
      ]
    },
    "sensor": {
      "$ref": "#/$defs/ObjectId"
    },
    "sensorId": {
      "type": "string"
    },
    "sensorIdDec": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "$ref": "#/$defs/Double"
        },
        {
          "type": "null"
        }
      ]
    },
    "snr": {
      "anyOf": [
        {
          "$ref": "#/$defs/Double"
        },
        {
          "type": "integer"
        }
      ]
    },
    "status": {
      "type": "string"
    }
  },
  "$defs": {
    "ObjectId": {
      "type": "object",
      "properties": {
        "$oid": {
          "type": "string",
          "pattern": "^[0-9a-fA-F]{24}$"
        }
      },
      "required": [
        "$oid"
      ],
      "additionalProperties": false
    },
    "Double": {
      "oneOf": [
        {
          "type": "number"
        },
        {
          "type": "object",
          "properties": {
            "$numberDouble": {
              "enum": [
                "Infinity",
                "-Infinity",
                "NaN"
              ]
            }
          }
        }
      ]
    },
    "Date": {
      "type": "object",
      "properties": {
        "$date": {
          "type": "string",
          "format": "date-time"
        }
      },
      "required": [
        "$date"
      ],
      "additionalProperties": false
    }
  }
}
```

### read@dashboardv2.alarms
*Alarm data*
**Definitely Relevant fields:**
- _id
- sensorIdDec = primary sensor lookup key for alarms
- `alertType` and `failureType`: (these are the same value always and not indicative of what the customer saw/input (must be populated based on analyst and/or FDE generated alert). For instance `250003735` has a failureType/alertType of "Closed Failure" but the customer entered "Not a Failure" to the field failureCause. This is critical because the only way for use to determine what actually happened is to review the `resolutionNotes` and `ackAction`)
- `resolutionNotes` (sometimes filled out with info such as: "Trap is ok with 140C inlet as per testing by Roberto on Jan. 8th 2026, the sensor may be loose and need to be reinstalled.")
- `failureCause` this is dropdown filled out with info such as "Mechanical Failure", "Dirt and Debris Buildup", "Not a Failure", "Other"
- ackAction (sometimes filled out with info such as: {"ackNotes":"Confirmed onsite by Troy (SXS) April 2, 2025","status":"Confirmed - Open Failure"})
- Combination of`detectedAt` and `resolvedOn` which are timestamps show when an issue was raised by Spirax and when it was addressed.
- type ("FDE", "Manual" or "None")


**Potential Relevant fields:**
- alarmData dict -> code, condition1...
- analystStatus ("CONFIRMED", "NOT_A_FAILURE"...)
- assessedBy
- resolvedBy


```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": [
    "_id",
    "alertType",
    "analystStatus",
    "assignees",
    "detectedAt"
  ],
  "properties": {
    "_id": {
      "$ref": "#/$defs/ObjectId"
    },
    "__v": {
      "type": "integer"
    },
    "acknowledged": {
      "type": "boolean"
    },
    "acknowledgedBy": {
      "$ref": "#/$defs/ObjectId"
    },
    "acknowledgedOn": {
      "$ref": "#/$defs/Date"
    },
    "alarmAction": {
      "anyOf": [
        {
          "type": "null"
        },
        {
          "type": "object",
          "required": [
            "actionToResolve",
            "failureCause",
            "failureType",
            "resolutionNotes"
          ],
          "properties": {
            "actionToResolve": {
              "type": "string"
            },
            "failureCause": {
              "type": "string"
            },
            "failureType": {
              "type": "string"
            },
            "resolutionNotes": {
              "type": "string"
            }
          }
        },
        {
          "type": "string"
        }
      ]
    },
    "alarmData": {
      "type": "object",
      "required": [
        "type"
      ],
      "properties": {
        "code": {
          "type": "integer"
        },
        "condition1": {
          "type": "boolean"
        },
        "condition2": {
          "type": "boolean"
        },
        "condition3": {
          "type": "boolean"
        },
        "condition4": {
          "type": "boolean"
        },
        "condition5": {
          "type": "boolean"
        },
        "condition6": {
          "type": "boolean"
        },
        "condition7": {
          "type": "boolean"
        },
        "conditions": {
          "type": "array",
          "items": {
            "type": [
              "integer",
              "string"
            ]
          }
        },
        "condTemp": {
          "type": "integer"
        },
        "description": {
          "type": "string"
        },
        "pipeTemp": {
          "type": "integer"
        },
        "type": {
          "type": "string"
        }
      }
    },
    "alertType": {
      "type": "string"
    },
    "analystStatus": {
      "type": "string"
    },
    "assessedBy": {
      "anyOf": [
        {
          "$ref": "#/$defs/ObjectId"
        },
        {
          "type": "string"
        }
      ]
    },
    "assignees": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/ObjectId"
      }
    },
    "createdBy": {
      "type": [
        "null",
        "string"
      ]
    },
    "detectedAt": {
      "$ref": "#/$defs/Date"
    },
    "isNotified": {
      "type": "boolean"
    },
    "resolved": {
      "type": "boolean"
    },
    "resolvedBy": {
      "anyOf": [
        {
          "type": "null"
        },
        {
          "$ref": "#/$defs/ObjectId"
        },
        {
          "type": "string"
        }
      ]
    },
    "resolvedOn": {
      "$ref": "#/$defs/Date"
    },
    "sensorIdDec": {
      "type": "integer"
    }
  },
  "$defs": {
    "ObjectId": {
      "type": "object",
      "properties": {
        "$oid": {
          "type": "string",
          "pattern": "^[0-9a-fA-F]{24}$"
        }
      },
      "required": [
        "$oid"
      ],
      "additionalProperties": false
    },
    "Date": {
      "type": "object",
      "properties": {
        "$date": {
          "type": "string",
          "format": "date-time"
        }
      },
      "required": [
        "$date"
      ],
      "additionalProperties": false
    }
  }
}
```




### read@dashboardv2.fdealarmsac
*NO DATA IN HERE???*


### read@dashboardv2.orgs
*Customer Site Info*
**Definitely Relevant fields:**
- _id
- name
- city

**Maybe Relevant fields:**
- notes

```json

{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": [
    "_id",
    "__v",
    "address",
    "createdAt",
    "email",
    "isFrozen",
    "name",
    "path",
    "updatedAt"
  ],
  "properties": {
    "_id": {
      "$ref": "#/$defs/ObjectId"
    },
    "__v": {
      "type": "integer"
    },
    "address": {
      "type": "object",
      "required": [
        "city",
        "line1",
        "line2",
        "postalCode",
        "region"
      ],
      "properties": {
        "city": {
          "type": [
            "string",
            "null"
          ]
        },
        "country": {
          "type": [
            "string",
            "null"
          ]
        },
        "line1": {
          "type": [
            "string",
            "null"
          ]
        },
        "line2": {
          "type": [
            "string",
            "null"
          ]
        },
        "postalCode": {
          "type": [
            "string",
            "null"
          ]
        },
        "region": {
          "type": [
            "string",
            "null"
          ]
        }
      }
    },
    "channelId": {
      "anyOf": [
        {
          "$ref": "#/$defs/ObjectId"
        },
        {
          "type": "null"
        }
      ]
    },
    "createdAt": {
      "$ref": "#/$defs/Date"
    },
    "email": {
      "type": [
        "string",
        "null"
      ]
    },
    "isFrozen": {
      "type": "boolean"
    },
    "name": {
      "type": "string"
    },
    "notes": {
      "type": [
        "null",
        "string"
      ]
    },
    "path": {
      "type": "string"
    },
    "updatedAt": {
      "$ref": "#/$defs/Date"
    },
    "website": {
      "type": [
        "string",
        "null"
      ]
    }
  },
  "$defs": {
    "ObjectId": {
      "type": "object",
      "properties": {
        "$oid": {
          "type": "string",
          "pattern": "^[0-9a-fA-F]{24}$"
        }
      },
      "required": [
        "$oid"
      ],
      "additionalProperties": false
    },
    "Date": {
      "type": "object",
      "properties": {
        "$date": {
          "type": "string",
          "format": "date-time"
        }
      },
      "required": [
        "$date"
      ],
      "additionalProperties": false
    }
  }
}
```
