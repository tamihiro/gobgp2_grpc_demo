# gobgp2_grpc_demo
Python implementation of gRPC client for GoBGPd 2.0

## About
Demonstrates how to call AddPath/DeletePath/ListPath gRPC to GoBGPd and unpack the response message in Python.

Works with golang 1.11.5, GoBGP 2.0, gRPC 1.19.0, and grpcio 1.18.0.

For older versions of GoBGP, please refer to [my previous demo code](https://github.com/tamihiro/gobgp_grpc_demo).

## How to use

After cloning this repo, cd to the directory and generate server and client interface from GoBGP proto files.
```
$ PATH_API=$GOPATH/src/github.com/osrg/gobgp/api ; \
python -m grpc_tools.protoc -I${PATH_API} --python_out=. --grpc_python_out=. ${PATH_API}/gobgp.proto ${PATH_API}/attribute.proto ${PATH_API}/capability.proto
```

Originate 10.0.0.1/32 with the path-attribute origin igp (default), nexthop 192.0.2.1, and communities [65004:999, no-export]:
```
$ python modpath.py 10.0.0.1/32 add -n 192.0.2.1 -c 65004:999 no-export
```

Search route in global RIB:
```
$ python getrib.py 10.0.0.1/32
10.0.0.1/32
  age: seconds: 1550205823
  best: True
  family: afi: AFI_IP, safi: SAFI_UNICAST
  filtered: False
  identifier: 0
  is_from_external: False
  is_nexthop_invalid: False
  is_withdraw: False
  local_identifier: 1
  neighbor_ip: <nil>
  nlri_binary: 
  no_implicit_withdraw: False
  pattrs_binary: []
  origin: igp
  communities: ['6504:999', '65535:65281']
  next_hop: 192.0.2.1
  source_asn: 0
  source_id: <nil>
  stale: False
  uuid: 
  validation:
```
  
Withdraw an announced route:
```
$ python modpath.py 10.0.0.1/32 delete
```

For more options:
```
$ python modpath.py -h
$ python modpath.py network add -h
$ python getrib.py -h
```

Default address family is ipv4-unicast, and "-6" option is available for ipv6-unicast.

Feel free to modify the code if you want to play with other address families.
