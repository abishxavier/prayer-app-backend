# -*- coding: utf-8 -*-
"""Official Agora AccessToken2 / RtcTokenBuilder2 implementation for Python 3."""

import base64
import hmac
import secrets
import struct
import time
import zlib
from collections import OrderedDict
from hashlib import sha256

VERSION_LENGTH = 3
Role_Publisher = 1
Role_Subscriber = 2


def pack_uint16(x):
    return struct.pack('<H', int(x))


def pack_uint32(x):
    return struct.pack('<I', int(x))


def pack_string(string):
    if isinstance(string, str):
        string = string.encode('utf-8')
    return pack_uint16(len(string)) + string


def pack_map_uint32(m):
    buffer = pack_uint16(len(m))
    for k, v in m.items():
        buffer += pack_uint16(k) + pack_uint32(v)
    return buffer


def get_version():
    return '007'


class Service:
    def __init__(self, service_type):
        self.__type = service_type
        self.__privileges = {}

    def add_privilege(self, privilege, expire):
        self.__privileges[privilege] = expire

    def service_type(self):
        return self.__type

    def pack(self):
        privileges = OrderedDict(
            sorted(iter(self.__privileges.items()), key=lambda x: int(x[0]))
        )
        return pack_uint16(self.__type) + pack_map_uint32(privileges)


class ServiceRtc(Service):
    kServiceType = 1
    kPrivilegeJoinChannel = 1
    kPrivilegePublishAudioStream = 2
    kPrivilegePublishVideoStream = 3
    kPrivilegePublishDataStream = 4

    def __init__(self, channel_name='', uid=0):
        super(ServiceRtc, self).__init__(ServiceRtc.kServiceType)
        self.__channel_name = channel_name.encode('utf-8') if isinstance(channel_name, str) else channel_name
        self.__uid = b'' if uid == 0 else str(uid).encode('utf-8')

    def pack(self):
        return super(ServiceRtc, self).pack() + pack_string(self.__channel_name) + pack_string(self.__uid)


class AccessToken2:
    def __init__(self, app_id='', app_certificate='', issue_ts=0, expire=86400):
        self.app_id = app_id
        self.app_certificate = app_certificate
        self.issue_ts = issue_ts if issue_ts > 0 else int(time.time())
        self.expire = expire
        self.salt = secrets.SystemRandom().randint(1, 99999999)
        self.services = {}

    def add_service(self, service):
        self.services[service.service_type()] = service

    def build(self):
        signing = self.__get_signing()
        signature = hmac.new(signing, self.__get_signing_data(), sha256).digest()
        content = self.__pack_content(signature)
        compressed = zlib.compress(content)
        return get_version() + base64.b64encode(compressed).decode('utf-8')

    def __get_signing(self):
        val = pack_uint32(self.issue_ts)
        return hmac.new(self.app_certificate.encode('utf-8'), val, sha256).digest()

    def __get_signing_data(self):
        signing_data = pack_string(self.app_id.encode('utf-8')) + \
                       pack_uint32(self.issue_ts) + \
                       pack_uint32(self.expire) + \
                       pack_uint32(self.salt) + \
                       pack_uint16(len(self.services))
        for _, service in sorted(self.services.items(), key=lambda x: x[0]):
            signing_data += service.pack()
        return signing_data

    def __pack_content(self, signature):
        return pack_string(signature) + self.__get_signing_data()


class RtcTokenBuilder2:
    @staticmethod
    def build_token_with_uid(app_id, app_certificate, channel_name, uid, role, token_expire=86400, privilege_expire=86400):
        token = AccessToken2(app_id, app_certificate, 0, token_expire)
        service_rtc = ServiceRtc(channel_name, uid)
        service_rtc.add_privilege(ServiceRtc.kPrivilegeJoinChannel, privilege_expire)
        if role in (Role_Publisher, 1):
            service_rtc.add_privilege(ServiceRtc.kPrivilegePublishAudioStream, privilege_expire)
            service_rtc.add_privilege(ServiceRtc.kPrivilegePublishVideoStream, privilege_expire)
            service_rtc.add_privilege(ServiceRtc.kPrivilegePublishDataStream, privilege_expire)
        token.add_service(service_rtc)
        return token.build()
