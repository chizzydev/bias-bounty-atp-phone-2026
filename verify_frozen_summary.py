#!/usr/bin/env python3
"""Verify frozen aggregate evidence copied verbatim from the SHA-manifested P0E packet.
This is NOT a substitute for a raw-input rerun or proof of current source-phone correctness.
"""
import csv, pathlib, sys
D=pathlib.Path(__file__).parent/'data'
def get(name):
 with open(D/name,newline='',encoding='utf-8-sig') as f:return list(csv.DictReader(f))
b=get('ATP-PHONE-P0B-region-summary.csv');c=get('ATP-PHONE-P0C-region-summary.csv');d=get('ATP-PHONE-P0D-A-region-summary.csv');f=get('ATP-PHONE-P0D-A-family-summary.csv')
assert len(b)==5 and sum(int(x['eligible_records']) for x in b)==22437
assert sum(int(x['not_preserved']) for x in b)==22437
assert sum(int(x['not_preserved']) for x in b if x['region']!='eastern-wa')==21608
assert len(c)==4 and sum(int(x['matched_pairs']) for x in c)==6505
assert sum(int(x['controls_with_phone']) for x in c)==6245
assert all(float(x['exposed_phone_rate'])==0 for x in c)
assert sum(int(x['losses']) for x in f)==4711
assert {x['service_family']:int(x['losses']) for x in f}=={'ESSENTIAL_SUPPLIES':4480,'MEDICAL_CONTACT':231}
print('FROZEN_AGGREGATE_CERTIFICATE=PASS')
print('PHONE_OMISSIONS_FIVE_PACKAGES=22437')
print('PHONE_OMISSIONS_PRIMARY_FOUR_REGIONS=21608')
print('PRIMARY_MATCHED_PAIRS=6505')
print('CONTROLS_VALID_NATIVE_PHONES=6245')
print('CONTROL_PHONE_RATE=%.8f%%'%(6245/6505*100))
print('OPERATIONAL_LOSSES=4711 MEDICAL_SUBSET=231')
print('SCOPE=AGGREGATE_TABLE_CHECK_NOT_RAW_INPUT_REPRODUCTION')
