// ============================================================================
//  MongoDB Replica Set Initialization
// ============================================================================
//  This defines the 3-node replica set "rs0". It is run exactly once by the
//  `mongo-init` helper container (see run-init.sh) when the environment first
//  boots.
//
//  - mongo-primary is given the highest priority (2) so it is elected PRIMARY.
//  - mongo-sec-1 and mongo-sec-2 are ordinary SECONDARIES (priority 1).
//
//  With 3 voting members, a "majority" is 2 nodes. Remember that number:
//  it is the whole point of the Session 1 CAP experiment. If you pause TWO
//  secondaries, the primary can no longer reach a majority, and w:majority
//  writes will block. (See README, "The CAP Theorem Experiment".)
// ============================================================================

rs.initiate({
  _id: "rs0",
  members: [
    { _id: 0, host: "mongo-primary:27017", priority: 2 },
    { _id: 1, host: "mongo-sec-1:27017",   priority: 1 },
    { _id: 2, host: "mongo-sec-2:27017",   priority: 1 }
  ]
});
