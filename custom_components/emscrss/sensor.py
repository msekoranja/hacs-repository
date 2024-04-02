"""Sensor platform for emscrss."""
from .const import DEFAULT_NAME, DOMAIN, ICON, SENSOR

from dateutil import tz
from datetime import timedelta, datetime

import logging

import json
from geopy import distance
import urllib.request
from urllib.error import HTTPError

import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import (
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_NAME,
    CONF_RADIUS,
    CONF_URL,
)
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity

_LOGGER = logging.getLogger(__name__)

CONF_MAGNITUDE = "magnitude"
CONF_AGE = "age"

DEFAULT_URL = "https://www.emsc-csem.org/service/api/1.6/get.geojson"
DEFAULT_RADIUS_IN_KM = 300.0
DEFAULT_MAGNITUDE = 3.0
DEFAULT_AGE_HOURS = 24

SCAN_INTERVAL = timedelta(minutes=5)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_URL, default=DEFAULT_URL): cv.string,
        vol.Optional(CONF_LATITUDE): cv.latitude,
        vol.Optional(CONF_LONGITUDE): cv.longitude,
        vol.Optional(CONF_RADIUS, default=DEFAULT_RADIUS_IN_KM): vol.Coerce(float),
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_MAGNITUDE, default=DEFAULT_MAGNITUDE): vol.Coerce(float),
        vol.Optional(CONF_AGE, default=DEFAULT_AGE_HOURS): vol.Coerce(float),
    }
)


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the EMSC component."""
    name = config.get(CONF_NAME)
    latitude = config.get(CONF_LATITUDE, hass.config.latitude)
    longitude = config.get(CONF_LONGITUDE, hass.config.longitude)
    url = config.get(CONF_URL)
    radius_in_km = config.get(CONF_RADIUS)
    magnitude = config.get(CONF_MAGNITUDE)
    age = timedelta(hours=config.get(CONF_AGE))
    utc_offset = hass.config.time_zone

    _LOGGER.debug(
        "latitude=%s, longitude=%s, url=%s, radius=%s, magintude=%s, age=%s, utc_offset=%s",
        latitude,
        longitude,
        url,
        radius_in_km,
        magnitude,
        age,
        utc_offset,
    )

    # Create all sensors based on categories.
    devices = []
    device = EMSCRSSServiceSensor(
        name, (latitude, longitude), url, radius_in_km, magnitude, age, utc_offset
    )
    devices.append(device)
    add_entities(devices, True)


class EMSCRSSServiceSensor(Entity):
    """Representation of a Sensor."""

    def __init__(self, service_name, coordinates, url, radius, magnitude, age, utc_offset):
        """Initialize the sensor."""
        self._service_name = service_name
        self._coordinates = coordinates
        self._radius = radius
        self._magnitude = magnitude
        self._utc_offset = utc_offset
        self._url = url
        self._state = None
        self._state_attributes = None

        self._feed = None

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"{self._service_name}"

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return None

    @property
    def icon(self):
        """Return the default icon to use in the frontend."""
        return ICON

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._state_attributes

    def update(self):
        """Update this sensor from the EMSC service."""
        try:
            from_zone = tz.gettz('UTC')
            to_zone = tz.gettz(self._utc_offset)
            contents = urllib.request.urlopen(self._url).read()
            geojson = json.loads(contents)
            data = {}
            entries = []
            for leaf in geojson['features']:
                item = leaf['properties']
                distance_to = round(distance.distance((self._coordinates[0], self._coordinates[1]), (item['location']["lat"], item['location']["lon"])).km)
                if distance_to < self._radius and item['magnitude']['mag'] >= self._magnitude:
                    feed_entry = {}
                    feed_entry["title"] = item['place']['region']
                    feed_entry["magnitude"] = item['magnitude']['mag']
                    feed_entry["time"] = datetime.fromtimestamp(float(item['time']['time'])).replace(tzinfo=from_zone).astimezone(to_zone).isoformat()
                    feed_entry["distance"] = distance_to
                    feed_entry["link"] = item['url']
                    if len(item['maps']) > 0:
                        if item['maps'].get('seismicity'):
                            feed_entry['imglink'] = item['maps']['seismicity']
                        elif item['maps'].get('intensity'):
                            feed_entry['imglink'] = item['maps']['intensity']
                        else:
                            feed_entry['imglink'] = ''
                    else:
                        feed_entry['imglink'] = ''
                    entries.append(feed_entry)
            data["earthquakes"] = entries
            self._state = len(data["earthquakes"])
            self._state_attributes = data
        except HTTPError as err:
            _LOGGER.warning(
                "Update not successful %s", err
            )
            self._state = 0
            self._state_attributes = {}
