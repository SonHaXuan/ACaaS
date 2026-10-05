package main

import (
	"encoding/json"
	"fmt"
	"sync"
	"time"
)

// LogEntry represents an immutable access log on LogChain.
type LogEntry struct {
	TxID          string         `json:"tx_id"`
	BlockNumber   int            `json:"block_number"`
	RequestID     string         `json:"request_id"`
	EdgeID        string         `json:"edge_id"`
	SeqE          int            `json:"seq_e"`
	SubjectID     string         `json:"subject_id"`
	Role          string         `json:"role"`
	Department    string         `json:"department"`
	Clearance     int            `json:"clearance_level"`
	PatientID     string         `json:"patient_id"`
	ResourceType  string         `json:"resource_type"`
	Action        string         `json:"action"`
	Decision      string         `json:"decision"`
	PolicyID      string         `json:"policy_id"`
	PolicyVersion int            `json:"policy_version"`
	PolicyHash    string         `json:"policy_hash"`
	Reason        string         `json:"reason"`
	LatencyMs     float64        `json:"latency_ms"`
	GapStatus     string         `json:"gap_status"`
	CommittedAt   float64        `json:"committed_at"`
	RawPayload    map[string]any `json:"raw_payload"`
}

// LogChainState manages the append-only LogChain ledger.
type LogChainState struct {
	mu       sync.RWMutex
	logs     []*LogEntry
	lastSeqE map[string]int // edge_id -> last_seq_e
}

// NewLogChainState initializes the state.
func NewLogChainState() *LogChainState {
	return &LogChainState{
		logs:     make([]*LogEntry, 0),
		lastSeqE: make(map[string]int),
	}
}

// AppendLog validates monotonic sequence seq_e per edge, detects gaps, and appends to LogChain.
func (s *LogChainState) AppendLog(entry map[string]any, txID string) (*LogEntry, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	edgeID, _ := entry["edge_id"].(string)
	if edgeID == "" {
		edgeID = "edge-node-1"
	}

	seqE := 0
	if val, ok := entry["seq_e"]; ok {
		switch v := val.(type) {
		case float64:
			seqE = int(v)
		case int:
			seqE = v
		}
	}

	lastSeq := s.lastSeqE[edgeID]
	gapStatus := "OK"
	if seqE > 0 {
		if lastSeq > 0 && seqE != lastSeq+1 {
			gapStatus = fmt.Sprintf("GAP_DETECTED{edge:%s, expected:%d, got:%d}", edgeID, lastSeq+1, seqE)
		}
		s.lastSeqE[edgeID] = seqE
	}

	blockNumber := len(s.logs)
	nowSec := float64(time.Now().UnixNano()) / 1e9

	reqID, _ := entry["request_id"].(string)
	subID, _ := entry["subject_id"].(string)
	role, _ := entry["role"].(string)
	dept, _ := entry["department"].(string)
	patientID, _ := entry["patient_id"].(string)
	resType, _ := entry["resource_type"].(string)
	action, _ := entry["action"].(string)
	decision, _ := entry["decision"].(string)
	policyID, _ := entry["policy_id"].(string)
	policyHash, _ := entry["policy_hash"].(string)
	reason, _ := entry["reason"].(string)

	clearance := 1
	if cl, ok := entry["clearance_level"].(float64); ok {
		clearance = int(cl)
	}

	policyVer := 0
	if pv, ok := entry["policy_version"].(float64); ok {
		policyVer = int(pv)
	}

	latencyMs := 0.0
	if lat, ok := entry["latency_ms"].(float64); ok {
		latencyMs = lat
	}

	record := &LogEntry{
		TxID:          txID,
		BlockNumber:   blockNumber,
		RequestID:     reqID,
		EdgeID:        edgeID,
		SeqE:          seqE,
		SubjectID:     subID,
		Role:          role,
		Department:    dept,
		Clearance:     clearance,
		PatientID:     patientID,
		ResourceType:  resType,
		Action:        action,
		Decision:      decision,
		PolicyID:      policyID,
		PolicyVersion: policyVer,
		PolicyHash:    policyHash,
		Reason:        reason,
		LatencyMs:     latencyMs,
		GapStatus:     gapStatus,
		CommittedAt:   nowSec,
		RawPayload:    entry,
	}

	s.logs = append(s.logs, record)
	return record, nil
}

// GetLogs returns all logs or filtered by subject/patient.
func (s *LogChainState) GetLogs(subjectID, patientID string) []*LogEntry {
	s.mu.RLock()
	defer s.mu.RUnlock()

	var result []*LogEntry
	for _, l := range s.logs {
		if subjectID != "" && l.SubjectID != subjectID {
			continue
		}
		if patientID != "" && l.PatientID != patientID {
			continue
		}
		result = append(result, l)
	}
	return result
}
