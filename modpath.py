#!-*- coding:utf-8 -*-

from __future__ import print_function

import grpc
from google.protobuf.any_pb2 import Any
import gobgp_pb2
import gobgp_pb2_grpc
import attribute_pb2
from uuid import UUID
import sys
import socket
import ipaddress
import argparse

_AF_NAME = dict()
_AF_NAME[4] = gobgp_pb2.Family(afi=gobgp_pb2.Family.AFI_IP, safi=gobgp_pb2.Family.SAFI_UNICAST)
_AF_NAME[6] = gobgp_pb2.Family(afi=gobgp_pb2.Family.AFI_IP6, safi=gobgp_pb2.Family.SAFI_UNICAST)

_ATTR_ORIGIN = dict()
_ATTR_ORIGIN['igp']        = 0
_ATTR_ORIGIN['egp']        = 1
_ATTR_ORIGIN['incomplete'] = 2 

_ATTR_COMM = dict()
_ATTR_COMM['internet']                   = int("0x00000000", 16)
_ATTR_COMM['planned-shut']               = int("0xffff0000", 16)
_ATTR_COMM['accept-own']                 = int("0xffff0001", 16)
_ATTR_COMM['route-filter-translated-v4'] = int("0xffff0002", 16)
_ATTR_COMM['route-filter-v4']            = int("0xffff0003", 16)
_ATTR_COMM['route-filter-translated-v6'] = int("0xffff0004", 16)
_ATTR_COMM['route-filter-v6']            = int("0xffff0005", 16)
_ATTR_COMM['llgr-stale']                 = int("0xffff0006", 16)
_ATTR_COMM['no-llgr']                    = int("0xffff0007", 16)
_ATTR_COMM['blackhole']                  = int("0xffff029a", 16)
_ATTR_COMM['no-export']                  = int("0xffffff01", 16)
_ATTR_COMM['no-advertise']               = int("0xffffff02", 16)
_ATTR_COMM['no-export-subconfed']        = int("0xffffff03", 16)
_ATTR_COMM['no-peer']                    = int("0xffffff04", 16)

def invalidate(k, v):
  print("invalid {}: {}".format(k, v), file=sys.stderr)
  sys.exit(-1)

def run(network, af, gobgpd_addr, timeout, withdraw, **kw):
  # family
  try:
    family = _AF_NAME[af]
  except:
    invalidate("address family", af)
    
  # nlri
  nlri = Any()
  try:
    prefix = network.split("/")[0]
    getattr(ipaddress, 'IPv'+str(af)+'Address')(unicode(prefix))
    prefix_len = int(network.split("/")[1])
    nlri.Pack(attribute_pb2.IPAddressPrefix(
      prefix_len = prefix_len,
      prefix = prefix,
      ))
  except:
    invalidate("prefix", prefix)
    
  # add or delete  
  stub_method = withdraw and "DeletePath" or "AddPath"
  
  attributes = []
  if af == 4:
    # nexthop
    if kw.get('nexthop'):
      nexthop = Any()
      try:
        nexthop.Pack(attribute_pb2.NextHopAttribute(next_hop=kw['nexthop']))
      except:
        invalidate("next-hop", kw['nexthop'])
      attributes.append(nexthop)
  else:
    mp_nlri_attribute = Any()
    nlris = [nlri]
    # nexthop
    next_hops = []
    if kw.get('nexthop'):
      next_hops.append(kw['nexthop'])
    mp_nlri_attribute.Pack(attribute_pb2.MpReachNLRIAttribute(family=family,nlris=nlris,next_hops=next_hops))
    attributes.append(mp_nlri_attribute)
  if not withdraw:
    # origin
    if kw.get('origin'):
      origin = Any()
      try:
        origin.Pack(attribute_pb2.OriginAttribute(origin=_ATTR_ORIGIN[kw['origin']]))
      except:
        invalidate("origin", kw['origin'])
      attributes.append(origin)
    # med
    if kw.get('med'):
      med = Any()
      try:
        med.Pack(attribute_pb2.MultiExitDiscAttribute(med=kw['med']))
      except:
        invalidate("med", kw['med'])
      attributes.append(med)
    # local_pref
    if kw.get('local_pref'):
      local_pref = Any()
      try:
        local_pref.Pack(attribute_pb2.LocalPrefAttribute(local_pref=kw['local_pref']))
      except:
        invalidate("local preference", kw['local_pref'])
      attributes.append(local_pref)
    # communities
    if kw.get('comms'):
      communities = Any()
      comms = []
      try:
        for s in kw['comms'].split(","):
          if s in _ATTR_COMM:
            comms.append(_ATTR_COMM[s])
          else:
            comms.append((int(s.split(':')[0]) << 16) + int(s.split(':')[1]))
        communities.Pack(attribute_pb2.CommunitiesAttribute(communities=comms))
      except:
        #invalidate("communities", kw['comms'])
        raise
      attributes.append(communities)
      
  channel = grpc.insecure_channel(gobgpd_addr + ":50051")
  stub = gobgp_pb2_grpc.GobgpApiStub(channel)

  # get source_as from server's global config
  try:
    global_conf = stub.GetBgp(gobgp_pb2.GetBgpRequest(), timeout)
    for c in global_conf.ListFields()[0]:
      if c.__class__.__name__ == "Global":
        for f in c.ListFields():
          if f[0].__class__.__name__ == "FieldDescriptor" and f[0].name == "as":
            source_asn = f[1]
            break
  except:
    print("failed to get source_asn from server's global config.", file=sys.stderr)
    source_asn = 0
      
  res = getattr(stub, stub_method)(
          getattr(gobgp_pb2, stub_method + "Request")(
            table_type=gobgp_pb2.GLOBAL,
            path=gobgp_pb2.Path(
                nlri=nlri,
                pattrs=attributes,
                family=family,
                source_asn=source_asn,
              )
            ),
            timeout,
          )
  if not withdraw:
    print(str(UUID(bytes=res.uuid)))
      
def main():
  parser = argparse.ArgumentParser(prog=sys.argv[0], )
  parser.add_argument('network', action='store')
  parser.add_argument('-r', action='store', default="localhost", dest="gobgpd_addr", help="GoBGPd address (default: localhost)")
  parser.add_argument('-n', action='store', dest="nexthop", default="0.0.0.0", help="Next-hop (default: 0.0.0.0)")
  parser.add_argument('-t', action='store', dest="timeout", type=int, default=1, help="Timeout second (default: 1)")
  parser_afg = parser.add_mutually_exclusive_group()
  parser_afg.add_argument('-4', action='store_const', dest="af", const=4, help="Address-family ipv4-unicast (default)")
  parser_afg.add_argument('-6', action='store_const', dest="af", const=6, help="Address-family ipv6-unicast")
  subparsers = parser.add_subparsers(dest="subcommand", help="sub-command help")
  parser_m = subparsers.add_parser('add', help="advertise prefix")
  parser_m.add_argument('-o', action='store', dest="origin", default="igp", help="Origin (default: igp)")
  parser_m.add_argument('-m', action='store', type=int, dest="med", help="MED")
  parser_m.add_argument('-p', action='store', type=int, dest="local_pref", help="Local-preference")
  parser_m.add_argument('-c', action='store', nargs='*', dest="comms", help="Community")
  parser_d = subparsers.add_parser('delete', help="withdraw prefix")
  argopts = parser.parse_args()

  try:
    socket.getaddrinfo(argopts.gobgpd_addr, 0)
  except socket.gaierror, e:
    invalidate("host", argopts.gobgpd_addr)

  withdraw = False
  if argopts.subcommand == "delete":
    withdraw = True

  pattrs = {k:v for k, v in argopts.__dict__.items()
             if k not in ("network", "af", "gobgpd_addr", "timeout", "withdraw", "comms", )
               and v is not None
            }
  if getattr(argopts, "comms", None):
    pattrs['comms'] = ",".join(argopts.comms)
  
  run(argopts.network, argopts.af or 4, argopts.gobgpd_addr, argopts.timeout, withdraw, **pattrs)

if __name__ == '__main__':
  main()
      
