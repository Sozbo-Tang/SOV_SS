#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""内存探针：打印本进程峰值 RSS。用法：python3 mem_probe.py [base|work]"""
import array
import resource
import sys

if len(sys.argv) > 1 and sys.argv[1] == "work":
    class U:
        __slots__ = ("uid", "side", "x", "y", "dx", "dy", "facing", "speed",
                     "hp", "count", "reload_t", "supp", "morale", "tid")

    us = [U() for _ in range(600)]
    for i, u in enumerate(us):
        u.uid = i; u.side = i % 2; u.x = i * 137 % 200000; u.y = i * 911 % 200000
        u.hp = 100; u.count = 3
    maps = [array.array('i', bytes(160000)) for _ in range(3)]   # 3 张 200×200 int32 图
    cards = {f"card{i}": {"cost": i % 100, "armor": i % 50,
                          "weapons": [i, i, i], "veterancy": 0} for i in range(81)}

print(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
