package main

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"sync"
)

// PeerEndorsement represents a proposal response endorsed by a specific peer.
type PeerEndorsement struct {
	PeerID    string `json:"peer_id"`
	OrgMSP    string `json:"org_msp"`
	Signature string `json:"signature"`
	Digest    string `json:"digest"`
	Valid     bool   `json:"valid"`
	Status    string `json:"status"` // "OK", "DROPPED", "INVALID_VERSION", "CONFLICTING_BODY"
}

// EndorsementResult holds the assembled envelope after endorsement policy verification.
type EndorsementResult struct {
	TxID          string            `json:"tx_id"`
	PolicyRule    string            `json:"policy_rule"`
	Satisfied     bool              `json:"satisfied"`
	Org1Endorsed  bool              `json:"org1_endorsed"`
	Org2Endorsed  bool              `json:"org2_endorsed"`
	PeerResponses []PeerEndorsement `json:"peer_responses"`
	FailureReason string            `json:"failure_reason,omitempty"`
}

// ByzantineConfig defines fault injection state for E11.
type ByzantineConfig struct {
	FaultyPeer string `json:"faulty_peer"` // e.g. "peer0.org2"
	Mode       string `json:"mode"`        // "honest", "passive", "rewind", "fork"
}

// EndorsementEngine manages 4-peer endorsement collection and AND(Org1, Org2) policy check.
type EndorsementEngine struct {
	mu     sync.RWMutex
	config ByzantineConfig
	peers  []string
}

// NewEndorsementEngine initializes the 4-peer ensemble.
func NewEndorsementEngine() *EndorsementEngine {
	return &EndorsementEngine{
		config: ByzantineConfig{
			FaultyPeer: "peer0.org2",
			Mode:       "honest",
		},
		peers: []string{"peer0.org1", "peer1.org1", "peer0.org2", "peer1.org2"},
	}
}

// SetByzantineMode configures fault injection for the designated peer.
func (e *EndorsementEngine) SetByzantineMode(faultyPeer, mode string) {
	e.mu.Lock()
	defer e.mu.Unlock()
	if faultyPeer != "" {
		e.config.FaultyPeer = faultyPeer
	}
	e.config.Mode = mode
}

// GetConfig returns the current fault injection configuration.
func (e *EndorsementEngine) GetConfig() ByzantineConfig {
	e.mu.RLock()
	defer e.mu.RUnlock()
	return e.config
}

// EndorseProposal collects endorsements from all 4 peers and verifies AND('Org1MSP.peer', 'Org2MSP.peer').
func (e *EndorsementEngine) EndorseProposal(proposalDigest string, proposalVersion int, currentVersion int) *EndorsementResult {
	e.mu.RLock()
	defer e.mu.RUnlock()

	var responses []PeerEndorsement
	org1ValidCount := 0
	org2ValidCount := 0

	// Calculate baseline proposal hash
	h := sha256.New()
	h.Write([]byte(fmt.Sprintf("%s:v%d", proposalDigest, proposalVersion)))
	canonicalDigest := hex.EncodeToString(h.Sum(nil))

	for _, peer := range e.peers {
		orgMSP := "Org1MSP"
		if peer == "peer0.org2" || peer == "peer1.org2" {
			orgMSP = "Org2MSP"
		}

		end := PeerEndorsement{
			PeerID: peer,
			OrgMSP: orgMSP,
			Digest: canonicalDigest,
			Valid:  true,
			Status: "OK",
		}

		// Inject Byzantine fault if this peer is configured faulty
		if peer == e.config.FaultyPeer && e.config.Mode != "honest" {
			switch e.config.Mode {
			case "passive":
				// Peer drops request / does not respond
				end.Valid = false
				end.Status = "DROPPED"
				end.Signature = ""
			case "rewind":
				// Peer signs outdated version (read-set rollback)
				staleDigest := fmt.Sprintf("%s:v%d:STALE", proposalDigest, currentVersion)
				sigHash := sha256.Sum256([]byte(staleDigest))
				end.Digest = staleDigest
				end.Signature = hex.EncodeToString(sigHash[:])
				end.Valid = false
				end.Status = "INVALID_VERSION"
			case "fork":
				// Peer signs conflicting body hash
				forkDigest := fmt.Sprintf("%s:FORK_DIFF_BODY", canonicalDigest)
				sigHash := sha256.Sum256([]byte(forkDigest))
				end.Digest = forkDigest
				end.Signature = hex.EncodeToString(sigHash[:])
				end.Valid = false
				end.Status = "CONFLICTING_BODY"
			}
		} else {
			// Honest peer signs canonical proposal digest
			sigHash := sha256.Sum256([]byte(peer + ":" + canonicalDigest))
			end.Signature = hex.EncodeToString(sigHash[:])
		}

		if end.Valid {
			if orgMSP == "Org1MSP" {
				org1ValidCount++
			} else if orgMSP == "Org2MSP" {
				org2ValidCount++
			}
		}

		responses = append(responses, end)
	}

	// Policy AND('Org1MSP.peer', 'Org2MSP.peer') requires at least 1 valid endorsement from Org1 and Org2
	org1Satisfied := org1ValidCount >= 1
	org2Satisfied := org2ValidCount >= 1
	allSatisfied := org1Satisfied && org2Satisfied

	result := &EndorsementResult{
		TxID:          canonicalDigest[:16],
		PolicyRule:    "AND('Org1MSP.peer','Org2MSP.peer')",
		Satisfied:     allSatisfied,
		Org1Endorsed:  org1Satisfied,
		Org2Endorsed:  org2Satisfied,
		PeerResponses: responses,
	}

	if !allSatisfied {
		if !org1Satisfied && !org2Satisfied {
			result.FailureReason = "Neither Org1 nor Org2 satisfied endorsement threshold"
		} else if !org1Satisfied {
			result.FailureReason = "Org1 failed endorsement threshold"
		} else {
			result.FailureReason = "Org2 failed endorsement threshold"
		}
	}

	return result
}
