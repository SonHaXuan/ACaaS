package main

import (
	"encoding/json"
	"fmt"
	"sync"
	"time"
)

// PolicyRecord represents an on-chain policy entry in PolicyChain.
type PolicyRecord struct {
	PolicyID    string    `json:"policy_id"`
	Version     int       `json:"version"`
	Hash        string    `json:"hash"`
	IssuerSig   string    `json:"issuer_sig"`
	PolicyBody  string    `json:"policy_body"`
	CommittedAt time.Time `json:"committed_at"`
	TxID        string    `json:"tx_id"`
}

// SyncEvent represents an update notification in SyncChain.
type SyncEvent struct {
	GlobalSeq   int       `json:"global_seq"`
	PolicyID    string    `json:"policy_id"`
	PrevVersion int       `json:"prev_version"`
	NewVersion  int       `json:"new_version"`
	Hash        string    `json:"hash"`
	IssuerSig   string    `json:"issuer_sig"`
	PolicyBody  any       `json:"policy_body"`
	EventType   string    `json:"event_type"`
	Timestamp   float64   `json:"timestamp"`
	TxID        string    `json:"tx_id"`
}

// PolicyChainState manages the ledger world state for policies.
type PolicyChainState struct {
	mu         sync.RWMutex
	policies   map[string]*PolicyRecord
	syncEvents []SyncEvent
	globalSeq  int
}

// NewPolicyChainState initializes the state.
func NewPolicyChainState() *PolicyChainState {
	return &PolicyChainState{
		policies:   make(map[string]*PolicyRecord),
		syncEvents: make([]SyncEvent, 0),
		globalSeq:  0,
	}
}

// CommitPolicy executes INV_mono on-chain and writes to PolicyChain and SyncChain.
func (s *PolicyChainState) CommitPolicy(
	policyID string,
	policyHash string,
	expectedPrevVersion int,
	issuerSig string,
	policyBodyJson string,
	txID string,
) (*PolicyRecord, *SyncEvent, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	currentVersion := 0
	if existing, found := s.policies[policyID]; found {
		currentVersion = existing.Version
	}

	// INV_mono verification: expectedPrevVersion must match current version exactly
	if expectedPrevVersion >= 0 && currentVersion != expectedPrevVersion {
		return nil, nil, fmt.Errorf("INV_mono violation on-chain: expected prev version %d, got %d", expectedPrevVersion, currentVersion)
	}

	newVersion := currentVersion + 1
	record := &PolicyRecord{
		PolicyID:    policyID,
		Version:     newVersion,
		Hash:        policyHash,
		IssuerSig:   issuerSig,
		PolicyBody:  policyBodyJson,
		CommittedAt: time.Now().UTC(),
		TxID:        txID,
	}
	s.policies[policyID] = record

	s.globalSeq++
	var bodyParsed any
	if err := json.Unmarshal([]byte(policyBodyJson), &bodyParsed); err != nil {
		bodyParsed = policyBodyJson
	}

	eventType := "CREATE"
	if policyHash == "" && currentVersion > 0 {
		eventType = "DELETE"
	} else if currentVersion > 0 {
		eventType = "UPDATE"
	}

	syncEv := SyncEvent{
		GlobalSeq:   s.globalSeq,
		PolicyID:    policyID,
		PrevVersion: currentVersion,
		NewVersion:  newVersion,
		Hash:        policyHash,
		IssuerSig:   issuerSig,
		PolicyBody:  bodyParsed,
		EventType:   eventType,
		Timestamp:   float64(time.Now().UnixNano()) / 1e9,
		TxID:        txID,
	}
	s.syncEvents = append(s.syncEvents, syncEv)

	return record, &syncEv, nil
}

// GetPolicy retrieves the latest record for a policy ID.
func (s *PolicyChainState) GetPolicy(policyID string) (*PolicyRecord, error) {
	s.mu.RUnlock()
	defer s.mu.RUnlock()

	rec, found := s.policies[policyID]
	if !found {
		return nil, fmt.Errorf("policy '%s' not found on ledger", policyID)
	}
	return rec, nil
}

// GetDelta returns SyncChain events in range (fromSeq, toSeq].
func (s *PolicyChainState) GetDelta(fromSeq, toSeq int) []SyncEvent {
	s.mu.RLock()
	defer s.mu.RUnlock()

	if toSeq <= 0 || toSeq > s.globalSeq {
		toSeq = s.globalSeq
	}

	var delta []SyncEvent
	for _, ev := range s.syncEvents {
		if ev.GlobalSeq > fromSeq && ev.GlobalSeq <= toSeq {
			delta = append(delta, ev)
		}
	}
	return delta
}

// GetCurrentGlobalSeq returns the current global sequence number.
func (s *PolicyChainState) GetCurrentGlobalSeq() int {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.globalSeq
}
