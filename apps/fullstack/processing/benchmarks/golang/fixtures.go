// Contrato portátil e composição do ciclo de cálculo sem acesso a banco.
package motor

import (
	"encoding/json"
	"fmt"
	"os"
	"sort"
)

// Caso contém somente entradas; Expected é usado exclusivamente pelos testes.
type Caso struct {
	ID             string            `json:"id"`
	Facts          []*Fact           `json:"facts"`
	Anomalies      []Anomaly         `json:"anomalies"`
	Quality        []SourceQuality   `json:"quality"`
	Baselines      []EntradaBaseline `json:"baselines"`
	WindowStart    Instante          `json:"window_start"`
	WindowEnd      Instante          `json:"window_end"`
	SimulatorEnd   *Instante         `json:"simulator_end"`
	Expected       json.RawMessage   `json:"expected"`
	ExpectedCounts map[string]int    `json:"expected_counts"`
}
type Documento struct {
	SchemaVersion       int    `json:"schema_version"`
	CatalogManifestHash string `json:"catalog_manifest_hash"`
	Cases               []Caso `json:"cases"`
	Case                *Caso  `json:"case"`
	Workloads           []Caso `json:"workloads"`
}

// LerDocumento rejeita versões desconhecidas, IDs duplicados e referências quebradas.
func LerDocumento(path string, catalog *Catalog) (Documento, error) {
	var doc Documento
	b, err := os.ReadFile(path)
	if err != nil {
		return doc, err
	}
	if err = json.Unmarshal(b, &doc); err != nil {
		return doc, err
	}
	if doc.SchemaVersion != 1 {
		return doc, fmt.Errorf("schema_version incompatível: %d", doc.SchemaVersion)
	}
	if doc.CatalogManifestHash != catalog.ManifestHash {
		return doc, fmt.Errorf("manifesto divergente: %s != %s", doc.CatalogManifestHash, catalog.ManifestHash)
	}
	seen := map[string]bool{}
	cases := append(append([]Caso{}, doc.Cases...), doc.Workloads...)
	if doc.Case != nil {
		cases = append(cases, *doc.Case)
	}
	if len(cases) == 0 {
		return doc, fmt.Errorf("documento sem casos")
	}
	for _, c := range cases {
		if c.ID == "" || seen[c.ID] {
			return doc, fmt.Errorf("ID de caso ausente ou duplicado: %q", c.ID)
		}
		seen[c.ID] = true
		facts := map[string]*Fact{}
		for _, f := range c.Facts {
			if f == nil || f.FactKey == "" {
				return doc, fmt.Errorf("fato sem chave: %s", c.ID)
			}
			if _, ok := facts[f.FactKey]; ok {
				return doc, fmt.Errorf("fato duplicado: %s", f.FactKey)
			}
			facts[f.FactKey] = f
		}
		for _, a := range c.Anomalies {
			if facts[a.FactKey] == nil {
				return doc, fmt.Errorf("fato da anomalia ausente: %s", a.FactKey)
			}
		}
	}
	return doc, nil
}
func (c Caso) anomalias() []Anomaly {
	facts := map[string]*Fact{}
	for _, f := range c.Facts {
		facts[f.FactKey] = f
	}
	anomalies := append([]Anomaly{}, c.Anomalies...)
	for i := range anomalies {
		anomalies[i].Fact = facts[anomalies[i].FactKey]
	}
	return anomalies
}
func (c Caso) EstadoInicial() map[ChaveBaseline]Baseline {
	state := map[ChaveBaseline]Baseline{}
	for _, b := range c.Baselines {
		state[b.Key] = b.Value
	}
	return state
}

func ExecutarRegras(c Caso, catalog *Catalog) (ResultadoRegras, error) {
	anomalies := c.anomalias()
	candidates := BuildCandidates(anomalies, c.Facts, c.Quality, catalog)
	return EvaluateCandidates(candidates, anomalies, c.Quality, catalog, LimitesPadrao())
}

// ExecutarCiclo é o fluxo de cálculo; não captura nem persiste dados de produção.
func ExecutarCiclo(c Caso, catalog *Catalog) (ResultadoCiclo, error) {
	quality := EvaluateQuality(c.Facts, catalog, c.WindowStart, c.WindowEnd, c.SimulatorEnd)
	anomalies, state := Detect(c.Facts, c.EstadoInicial(), catalog, DetectorPadrao())
	candidates := BuildCandidates(anomalies, c.Facts, quality, catalog)
	rules, err := EvaluateCandidates(candidates, anomalies, quality, catalog, LimitesPadrao())
	updates := make([]EntradaBaseline, 0, len(state))
	for k, v := range state {
		updates = append(updates, EntradaBaseline{k, v})
	}
	sort.Slice(updates, func(i, j int) bool {
		a, b := updates[i].Key, updates[j].Key
		for _, p := range [][2]string{{a.Source, b.Source}, {a.Entity, b.Entity}, {a.Metric, b.Metric}} {
			if p[0] != p[1] {
				return p[0] < p[1]
			}
		}
		return a.Hour < b.Hour
	})
	return ResultadoCiclo{rules, quality, anomalies, updates}, err
}
func Contagens(c Caso, r ResultadoCiclo) map[string]int {
	result := map[string]int{"facts": len(c.Facts), "anomalies": len(r.Anomalies), "candidates_prefiltered": r.CandidatesPrefiltered, "candidates_evaluated": r.CandidatesEvaluated, "candidates_truncated": r.CandidatesTruncated, "hypotheses": len(r.Hypotheses), "generated": 0, "insufficient_evidence": 0, "discarded": 0}
	for _, h := range r.Hypotheses {
		result[h.EvaluationStatus]++
	}
	return result
}

// ExecutarDocumento devolve saídas completas inclusive para as cargas maiores.
func ExecutarDocumento(doc Documento, catalog *Catalog) (map[string]any, error) {
	results := map[string]any{}
	for _, c := range doc.Cases {
		r, err := ExecutarRegras(c, catalog)
		if err != nil {
			return nil, err
		}
		results[c.ID] = r
	}
	cycles := append([]Caso{}, doc.Workloads...)
	if doc.Case != nil {
		cycles = append(cycles, *doc.Case)
	}
	for _, c := range cycles {
		r, err := ExecutarCiclo(c, catalog)
		if err != nil {
			return nil, err
		}
		results[c.ID] = r
	}
	return results, nil
}
