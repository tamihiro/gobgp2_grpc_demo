#! -*- coding:utf-8 -*-

from __future__ import print_function

import grpc
from google.protobuf.any_pb2 import Any
import gobgp_pb2
import gobgp_pb2_grpc
import attribute_pb2
import sys
import socket
import ipaddress
import argparse

_AF_NAME = dict()
_AF_NAME[4] = gobgp_pb2.Family(afi=gobgp_pb2.Family.AFI_IP, safi=gobgp_pb2.Family.SAFI_UNICAST)
_AF_NAME[6] = gobgp_pb2.Family(afi=gobgp_pb2.Family.AFI_IP6, safi=gobgp_pb2.Family.SAFI_UNICAST)

_TT = dict()
_TT['global'] = gobgp_pb2.GLOBAL
_TT['in'] = gobgp_pb2.ADJ_IN
_TT['out'] = gobgp_pb2.ADJ_OUT

_ATTR_ORIGIN = dict()
_ATTR_ORIGIN[0] = "igp"
_ATTR_ORIGIN[1] = "egp"
_ATTR_ORIGIN[2] = "incomplete" 

def compare_destinations(af):
  # sort nlri
  afcls = getattr(ipaddress, "IPv"+str(af)+"Network")
  def func(a, b):
    net_a = afcls(a.destination.prefix)
    net_b = afcls(b.destination.prefix)
    if not net_a.network_address == net_b.network_address:
      return int(net_a.network_address) - int(net_b.network_address)
    return int(net_a.netmask) - int(net_b.netmask)
  return func

def pb_msg_attrs(m):
  # return list of attr names
  slice_ind = -1 * len('_FIELD_NUMBER')
  return [ attr[:slice_ind].lower() for attr in dir(m) if attr.endswith('_FIELD_NUMBER') ]

def print_path(path):
  # print each Path message, unpack its attributes if appropriate
  nlri = attribute_pb2.IPAddressPrefix()
  path.nlri.Unpack(nlri)
  print("{}/{}".format(nlri.prefix, nlri.prefix_len))
  pattrs = []
  for attr_name in pb_msg_attrs(path):
    if attr_name == "nlri":
      continue
    if attr_name == "pattrs":
      for pattr in path.pattrs:
        pattr_name = pattr.type_url.split(".")[-1]
        pattr_cls = getattr(attribute_pb2, pattr_name, None)
        if pattr_cls:
          pattr_obj = pattr_cls()
          pattr.Unpack(pattr_obj)
          for k in pb_msg_attrs(pattr_obj):
            if k == "origin":
              # print corresponding value
              v = _ATTR_ORIGIN.get(getattr(pattr_obj, k, -1))
            elif k == "communities":
              # convert to a list of colon-delimited sets
              v = [ "{}:{}".format(int("0xffff",16)&c>>16, int("0xffff",16)&c) for c in getattr(pattr_obj, k, []) ]              
            else:
              # printing as is
              v = str(getattr(pattr_obj, k, "")).strip().replace("\n", ", ")                
            print("  {}: {}".format(k, v))
    else:
      print("  {}: {}".format(attr_name, str(getattr(path, attr_name, "")).strip().replace("\n", ", ")))
    
def invalidate(k, v):
  print("invalid {}: {}".format(k, v), file=sys.stderr)
  sys.exit(-1)

def run(af, gobgpd_addr, timeout, *network, **kw):
  # family
  try:
    family = _AF_NAME[af]
  except:
    invalidate("address family", af)
  # table_type, name
  if kw.get("rib_in_neighbor"):
    table_type = _TT['in']
    name = kw["rib_in_neighbor"]
  elif kw.get("rib_out_neighbor"):
    table_type = _TT['out']
    name = kw["rib_out_neighbor"]
  else:
    table_type = _TT['global']
    name= None
  # prefixes
  prefixes = []
  for n in network:
    try:
      getattr(ipaddress, 'IPv'+str(af)+'Network')(unicode(n))
      prefixes.append(gobgp_pb2.TableLookupPrefix(prefix=n))
    except:
      invalidate("prefix", n)
    
  channel = grpc.insecure_channel(gobgpd_addr + ":50051")
  stub = gobgp_pb2_grpc.GobgpApiStub(channel)
  res = stub.ListPath(
          gobgp_pb2.ListPathRequest(
            table_type=table_type,
            name=name,
            prefixes=prefixes,
            family=family,
            ),
          timeout,
          )
  destinations = []
  while True:
    try:
      destinations.append(res.next())
    except StopIteration:
      break
  destinations.sort(cmp=compare_destinations(af))
  for paths in [ d.destination.paths for d in destinations ]:
    for p in paths:
      print_path(p)
    
def main():
  parser = argparse.ArgumentParser()
  parser_afg = parser.add_mutually_exclusive_group()
  parser_afg.add_argument('-4', action='store_const', dest="af", const=4, help="Address-family ipv4-unicast (default)")
  parser_afg.add_argument('-6', action='store_const', dest="af", const=6, help="Address-family ipv6-unicast")
  parser_tg = parser.add_mutually_exclusive_group()
  parser_tg.add_argument('-l', action='store_true', dest="rib_local", help="Show local rib (default: true)")
  parser_tg.add_argument('-i', action='store', dest="rib_in_neighbor", help="Routes received from peer")
  parser_tg.add_argument('-o', action='store', dest="rib_out_neighbor", help="Routes advertised to peer")
  parser.add_argument('-r', action='store', default="localhost", dest="gobgpd_addr", help="GoBGPd address (default: localhost)")
  parser.add_argument('-t', action='store', dest="timeout", type=int, default=1, help="Timeout second (default: 1)")
  parser.add_argument('network', action='store', nargs='*')
  argopts = parser.parse_args()

  try:
    for a in ['gobgpd_addr', 'rib_in_neighbor', 'rib_out_neighbor', ]:
      if getattr(argopts, a):
        socket.gethostbyname(getattr(argopts, a))
  except socket.gaierror, e:
    invalidate("host", getattr(argopts,a))

  run(argopts.af or 4,
      argopts.gobgpd_addr,
      argopts.timeout,
      *argopts.network,
      rib_in_neighbor=argopts.rib_in_neighbor,
      rib_out_neighbor=argopts.rib_out_neighbor)

if __name__ == '__main__':
  main()


