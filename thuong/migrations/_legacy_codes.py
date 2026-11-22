"""Defaults used when replaying the schema before migration 0013."""

from uuid import uuid4


def tao_ma_tong_thuong():
    return 'T' + uuid4().hex[:24]


def tao_ma_de_xuat():
    return 'D' + uuid4().hex[:24]
