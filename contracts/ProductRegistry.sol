// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract ProductRegistry {
    struct Record {
        bytes32 dataHash;
        uint256 timestamp;
        address submitter;
    }

    mapping(string => Record) private records;
    event ProductRegistered(string indexed productId, bytes32 dataHash, uint256 timestamp, address indexed submitter);

    function registerProduct(string calldata productId, bytes32 dataHash) external {
        records[productId] = Record({dataHash: dataHash, timestamp: block.timestamp, submitter: msg.sender});
        emit ProductRegistered(productId, dataHash, block.timestamp, msg.sender);
    }

    function getProductHash(string calldata productId) external view returns (bytes32 dataHash, uint256 timestamp, address submitter) {
        Record memory r = records[productId];
        return (r.dataHash, r.timestamp, r.submitter);
    }
}
