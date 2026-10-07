// Package motor implementa o cálculo isolado do Argus para comparação com Python.
package motor

import (
	"encoding/json"
	"fmt"
	"time"
)

// Instante preserva o formato datetime.isoformat(), inclusive +00:00 e microssegundos.
type Instante struct{ time.Time }

func (t Instante) ISO() string {
	layout := "2006-01-02T15:04:05"
	if t.Nanosecond() != 0 {
		layout += ".000000"
	}
	return t.Format(layout + "-07:00")
}
func (t Instante) MarshalJSON() ([]byte, error) { return json.Marshal(t.ISO()) }
func (t *Instante) UnmarshalJSON(b []byte) error {
	var s string
	if err := json.Unmarshal(b, &s); err != nil {
		return err
	}
	v, err := time.Parse(time.RFC3339Nano, s)
	if err != nil {
		return err
	}
	t.Time = v
	return nil
}

type Fact struct {
	FactKey        string         `json:"fact_key"`
	VersionLSN     int64          `json:"version_lsn"`
	Role           string         `json:"role"`
	Kind           string         `json:"kind"`
	EventStart     Instante       `json:"event_start"`
	EventEnd       *Instante      `json:"event_end"`
	AvailableAt    Instante       `json:"available_at"`
	Source         string         `json:"source"`
	Entity         string         `json:"entity"`
	Metric         string         `json:"metric"`
	DimensionType  *string        `json:"dimension_type"`
	DimensionValue *string        `json:"dimension_value"`
	Value          *float64       `json:"value"`
	SampleSize     *int64         `json:"sample_size"`
	Attributes     map[string]any `json:"attributes"`
}
type Baseline struct {
	Mean        *float64  `json:"mean"`
	Variance    *float64  `json:"variance"`
	N           int       `json:"n"`
	LastEventAt *Instante `json:"last_event_at"`
}
type ChaveBaseline struct {
	Source, Entity, Metric string
	Hour                   int
}

func (k ChaveBaseline) MarshalJSON() ([]byte, error) {
	return json.Marshal([]any{k.Source, k.Entity, k.Metric, k.Hour})
}
func (k *ChaveBaseline) UnmarshalJSON(b []byte) error {
	var parts []json.RawMessage
	if err := json.Unmarshal(b, &parts); err != nil {
		return err
	}
	if len(parts) != 4 {
		return fmt.Errorf("chave de baseline precisa de quatro componentes")
	}
	for i, dest := range []any{&k.Source, &k.Entity, &k.Metric, &k.Hour} {
		if err := json.Unmarshal(parts[i], dest); err != nil {
			return err
		}
	}
	return nil
}

type EntradaBaseline struct {
	Key   ChaveBaseline `json:"key"`
	Value Baseline      `json:"value"`
}
type Anomaly struct {
	Fact             *Fact          `json:"-"`
	FactKey          string         `json:"fact_key"`
	Observed         float64        `json:"observed"`
	Expected         float64        `json:"expected"`
	Direction        string         `json:"direction"`
	Deviation        float64        `json:"deviation"`
	Z                float64        `json:"z"`
	Strength         float64        `json:"strength"`
	BaselineSnapshot map[string]any `json:"baseline_snapshot"`
	PersistedID      *int64         `json:"persisted_id"`
}
type SourceQuality struct {
	Source                 string         `json:"source"`
	ExpectedCadenceSeconds int            `json:"expected_cadence_seconds"`
	LastObservationAt      *Instante      `json:"last_observation_at"`
	Freshness              *float64       `json:"freshness"`
	Completeness           *float64       `json:"completeness"`
	Validity               *float64       `json:"validity"`
	Consistency            *float64       `json:"consistency"`
	QualityScore           *float64       `json:"quality_score"`
	Status                 string         `json:"status"`
	ExpectedBuckets        int            `json:"expected_buckets"`
	ObservedBuckets        int            `json:"observed_buckets"`
	Details                map[string]any `json:"details"`
}
type Feature struct {
	Name          string   `json:"name"`
	Applicability string   `json:"applicability"`
	Value         *float64 `json:"value"`
	Weight        float64  `json:"weight"`
	Contribution  *float64 `json:"contribution"`
	Explanation   string   `json:"explanation"`
}
type Evidence struct {
	Role        string         `json:"role"`
	Polarity    string         `json:"polarity"`
	Explanation string         `json:"explanation"`
	Fact        *Fact          `json:"-"`
	FactKey     *string        `json:"fact_key"`
	VersionLSN  *int64         `json:"version_lsn"`
	Observed    *float64       `json:"observed"`
	Expected    *float64       `json:"expected"`
	Strength    *float64       `json:"strength"`
	Quality     *float64       `json:"quality"`
	Attributes  map[string]any `json:"attributes"`
}
type Candidate struct {
	Family             string         `json:"family"`
	Kind               string         `json:"kind"`
	AnomalyIndex       *int           `json:"anomaly_index"`
	Subject            *Fact          `json:"-"`
	Supporting         []*Fact        `json:"-"`
	SubjectFactKey     *string        `json:"subject_fact_key"`
	SupportingFactKeys []string       `json:"supporting_fact_keys"`
	RequiredMissing    []string       `json:"required_missing"`
	Contrary           []Evidence     `json:"contrary"`
	Scope              map[string]any `json:"scope"`
	Title              string         `json:"title"`
	Summary            string         `json:"summary"`
	TemporalScore      *float64       `json:"temporal_score"`
	Specificity        *float64       `json:"specificity"`
}
type Hypothesis struct {
	Family                string         `json:"family"`
	Kind                  string         `json:"kind"`
	Title                 string         `json:"title"`
	Summary               string         `json:"summary"`
	Scope                 map[string]any `json:"scope"`
	EffectStart           Instante       `json:"effect_start"`
	EffectEnd             Instante       `json:"effect_end"`
	Score                 float64        `json:"score"`
	Coverage              float64        `json:"coverage"`
	Confidence            string         `json:"confidence"`
	EvaluationStatus      string         `json:"evaluation_status"`
	ContradictionStrength float64        `json:"contradiction_strength"`
	DedupKey              string         `json:"dedup_key"`
	LineageKey            string         `json:"lineage_key"`
	Features              []Feature      `json:"features"`
	Evidence              []Evidence     `json:"evidence"`
	AnomalyIndexes        []int          `json:"anomaly_indexes"`
}
type ResultadoRegras struct {
	Candidates            []Candidate  `json:"candidates"`
	Hypotheses            []Hypothesis `json:"hypotheses"`
	CandidatesPrefiltered int          `json:"candidates_prefiltered"`
	CandidatesEvaluated   int          `json:"candidates_evaluated"`
	CandidatesTruncated   int          `json:"candidates_truncated"`
}
type ResultadoCiclo struct {
	ResultadoRegras
	Quality         []SourceQuality   `json:"quality"`
	Anomalies       []Anomaly         `json:"anomalies"`
	BaselineUpdates []EntradaBaseline `json:"baseline_updates"`
}

func ptr[T any](v T) *T { return &v }
func numero(v *float64) float64 {
	if v == nil {
		return 0
	}
	return *v
}
func texto(v *string) string {
	if v == nil {
		return ""
	}
	return *v
}
func amostra(f *Fact) int64 {
	if f.SampleSize == nil {
		return 0
	}
	return *f.SampleSize
}
