package motor

import (
	"encoding/json"
	"fmt"
	"math"
	"reflect"
	"testing"
	"time"
)

func catalogoTeste(t testing.TB) *Catalog {
	t.Helper()
	c, err := CarregarCatalogo("../../src/argus_processing/catalogs")
	if err != nil {
		t.Fatal(err)
	}
	return c
}
func documentoTeste(t testing.TB, name string, c *Catalog) Documento {
	t.Helper()
	doc, err := LerDocumento("../fixtures/"+name, c)
	if err != nil {
		t.Fatal(err)
	}
	return doc
}
func conferir(t *testing.T, actual any, expected json.RawMessage) {
	t.Helper()
	b, err := json.Marshal(actual)
	if err != nil {
		t.Fatal(err)
	}
	var a, e any
	if err = json.Unmarshal(b, &a); err != nil {
		t.Fatal(err)
	}
	if err = json.Unmarshal(expected, &e); err != nil {
		t.Fatal(err)
	}
	compararJSON(t, a, e, "resultado")
}
func compararJSON(t *testing.T, a, e any, path string) {
	t.Helper()
	switch e := e.(type) {
	case map[string]any:
		m, ok := a.(map[string]any)
		if !ok || len(m) != len(e) {
			t.Fatalf("%s: chaves/tipo diferentes", path)
		}
		for k, v := range e {
			x, ok := m[k]
			if !ok {
				t.Fatalf("%s.%s ausente", path, k)
			}
			compararJSON(t, x, v, path+"."+k)
		}
	case []any:
		items, ok := a.([]any)
		if !ok || len(items) != len(e) {
			t.Fatalf("%s: tamanho/tipo diferentes", path)
		}
		for i, v := range e {
			compararJSON(t, items[i], v, fmt.Sprintf("%s[%d]", path, i))
		}
	case float64:
		v, ok := a.(float64)
		if !ok || math.Abs(v-e) > math.Max(1e-12, 1e-9*math.Max(math.Abs(v), math.Abs(e))) {
			t.Fatalf("%s: %v != %v", path, a, e)
		}
	default:
		if !reflect.DeepEqual(a, e) {
			t.Fatalf("%s: %v != %v", path, a, e)
		}
	}
}
func TestParidadeRegras(t *testing.T) {
	catalog := catalogoTeste(t)
	doc := documentoTeste(t, "regras_casos_v1.json", catalog)
	if len(doc.Cases) != 49 {
		t.Fatalf("esperados 49 casos; recebidos %d", len(doc.Cases))
	}
	for _, c := range doc.Cases {
		t.Run(c.ID, func(t *testing.T) {
			r, err := ExecutarRegras(c, catalog)
			if err != nil {
				t.Fatal(err)
			}
			conferir(t, r, c.Expected)
		})
	}
}
func TestParidadeCiclo(t *testing.T) {
	catalog := catalogoTeste(t)
	doc := documentoTeste(t, "ciclo_caso_v1.json", catalog)
	r, err := ExecutarCiclo(*doc.Case, catalog)
	if err != nil {
		t.Fatal(err)
	}
	conferir(t, r, doc.Case.Expected)
}
func TestContagensCargas(t *testing.T) {
	catalog := catalogoTeste(t)
	doc := documentoTeste(t, "cargas_v1.json", catalog)
	for _, c := range doc.Workloads {
		t.Run(c.ID, func(t *testing.T) {
			r, err := ExecutarCiclo(c, catalog)
			if err != nil {
				t.Fatal(err)
			}
			if !reflect.DeepEqual(Contagens(c, r), c.ExpectedCounts) {
				t.Fatalf("contagens: %v != %v", Contagens(c, r), c.ExpectedCounts)
			}
		})
	}
}
func TestDetectorCausalNaoMutaEntrada(t *testing.T) {
	catalog := catalogoTeste(t)
	doc := documentoTeste(t, "ciclo_caso_v1.json", catalog)
	c := *doc.Case
	before, _ := json.Marshal(c)
	first, err := ExecutarCiclo(c, catalog)
	if err != nil {
		t.Fatal(err)
	}
	second, err := ExecutarCiclo(c, catalog)
	if err != nil {
		t.Fatal(err)
	}
	a, _ := json.Marshal(first)
	b, _ := json.Marshal(second)
	after, _ := json.Marshal(c)
	if string(a) != string(b) || string(before) != string(after) {
		t.Fatal("execução não determinista ou entrada alterada")
	}
	state := map[ChaveBaseline]Baseline{}
	for _, entry := range first.BaselineUpdates {
		state[entry.Key] = entry.Value
	}
	repeated, _ := Detect(c.Facts, state, catalog, DetectorPadrao())
	if len(repeated) != 0 {
		t.Fatal("replay do mesmo instante gerou novas anomalias")
	}
}
func TestZonaCircadianaEPrecisaoTemporal(t *testing.T) {
	var at Instante
	if err := json.Unmarshal([]byte(`"2018-12-01T02:30:00.123400+00:00"`), &at); err != nil {
		t.Fatal(err)
	}
	if at.ISO() != "2018-12-01T02:30:00.123400+00:00" {
		t.Fatal(at.ISO())
	}
	// Em dezembro de 2018 São Paulo ainda tinha horário de verão.
	if at.In(zonaBRT).Hour() != 0 {
		t.Fatal("conversão BRT ignorou horário de verão")
	}
	f := &Fact{FactKey: "f", Role: "subject", Kind: "metric", EventStart: at, Value: ptr(10.0), Metric: "error_rate_pct", Source: "prometheus", Entity: "p"}
	_, state := Detect([]*Fact{f}, nil, catalogoTeste(t), DetectorPadrao())
	if state[ChaveBaseline{"prometheus", "p", "error_rate_pct", 0}].N != 1 {
		t.Fatal("baseline na hora incorreta")
	}
}
func TestCortesEDeduplicacaoEstaveis(t *testing.T) {
	catalog := catalogoTeste(t)
	doc := documentoTeste(t, "cargas_v1.json", catalog)
	c := doc.Workloads[3]
	q := EvaluateQuality(c.Facts, catalog, c.WindowStart, c.WindowEnd, c.SimulatorEnd)
	a, _ := Detect(c.Facts, c.EstadoInicial(), catalog, DetectorPadrao())
	candidates := BuildCandidates(a, c.Facts, q, catalog)
	first, err := EvaluateCandidates(candidates, a, q, catalog, Limites{7, 3, 2})
	if err != nil {
		t.Fatal(err)
	}
	for i, j := 0, len(candidates)-1; i < j; i, j = i+1, j-1 {
		candidates[i], candidates[j] = candidates[j], candidates[i]
	}
	second, err := EvaluateCandidates(candidates, a, q, catalog, Limites{7, 3, 2})
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(first.Hypotheses, second.Hypotheses) || first.CandidatesTruncated != second.CandidatesTruncated {
		t.Fatal("corte depende da ordem de entrada")
	}
	if first.CandidatesEvaluated != 7 || first.CandidatesTruncated < first.CandidatesPrefiltered-7 {
		t.Fatalf("corte incorreto: %d", first.CandidatesEvaluated)
	}
	generated := 0
	for _, h := range first.Hypotheses {
		if h.EvaluationStatus == "generated" {
			generated++
		}
	}
	if generated > 2 {
		t.Fatal("teto de geradas excedido")
	}
}
func TestQualidadeUsaDisponibilidadeEValorAusente(t *testing.T) {
	now := Instante{time.Date(2026, 7, 12, 15, 0, 0, 0, time.UTC)}
	f := &Fact{Role: "subject", Kind: "metric", Source: "npaw_geo", EventStart: Instante{now.Add(-28 * time.Hour)}, AvailableAt: now, Value: nil}
	q := EvaluateQuality([]*Fact{f}, catalogoTeste(t), Instante{now.Add(-time.Hour)}, now, &now)
	for _, item := range q {
		if item.Source == f.Source {
			if numero(item.Freshness) != 1 || item.Status != "invalid" || numero(item.Validity) != 0 {
				t.Fatalf("canário incorreto: %+v", item)
			}
			return
		}
	}
	t.Fatal("fonte ausente")
}

func TestDetectorLimiaresAquecimentoEDirecao(t *testing.T) {
	catalog := catalogoTeste(t)
	now := Instante{time.Date(2026, 7, 12, 15, 0, 0, 0, time.UTC)}
	for _, row := range []struct {
		name, metric   string
		mean, observed float64
		n, want        int
	}{
		{"cold_start", "latency_ms_avg", 100, 5000, 11, 0},
		{"latencia_em_log", "latency_ms_avg", 100, 900, 12, 1},
		{"apdex_melhora", "apdex", 0.95, 0.99, 12, 0},
		{"apdex_queda", "apdex", 0.95, 0.4, 12, 1},
		{"abaixo_z", "error_rate_pct", 1, 1.874, 12, 0},
		{"no_z", "error_rate_pct", 1, 1.875, 12, 1},
		{"sem_materialidade_relativa", "error_rate_pct", 100, 118, 12, 0},
		{"materialidade_relativa", "error_rate_pct", 100, 125, 12, 1},
	} {
		t.Run(row.name, func(t *testing.T) {
			mean := row.mean
			if catalog.Metric(row.metric).Transform == "log1p" {
				mean = math.Log1p(mean)
			}
			f := &Fact{FactKey: "f", Role: "subject", Kind: "metric", Source: "prometheus", Entity: "p", Metric: row.metric, Value: ptr(row.observed), EventStart: now}
			key := ChaveBaseline{f.Source, f.Entity, f.Metric, 12}
			state := map[ChaveBaseline]Baseline{key: {Mean: ptr(mean), Variance: ptr(0.0), N: row.n, LastEventAt: ptr(Instante{now.Add(-24 * time.Hour)})}}
			anomalies, next := Detect([]*Fact{f}, state, catalog, DetectorPadrao())
			if len(anomalies) != row.want {
				t.Fatalf("anomalias: %d != %d", len(anomalies), row.want)
			}
			if next[key].N != row.n+1 {
				t.Fatal("baseline não avançou")
			}
			if len(anomalies) > 0 && math.Abs(anomalies[0].Expected-row.mean) > 1e-9 {
				t.Fatal("expected não voltou à escala original")
			}
		})
	}
}

func TestScoreAusenciaZeroEContradicao(t *testing.T) {
	values := map[string]ValorFeature{}
	for _, p := range pesos {
		values[p.Name] = ValorFeature{"available", ptr(1.0), "teste"}
	}
	score, coverage, confidence, _ := ScoreFeatures(values, 0)
	if math.Abs(score-100) > 1e-12 || coverage != 1 || confidence != "high" {
		t.Fatal("score completo incorreto")
	}
	values["Q"] = ValorFeature{"unavailable", nil, "ausente"}
	_, missing, _, features := ScoreFeatures(values, 0)
	if features[5].Contribution != nil || missing >= 1 {
		t.Fatal("ausência virou contribuição")
	}
	values["Q"] = ValorFeature{"available", ptr(0.0), "zero"}
	_, zero, _, features := ScoreFeatures(values, 0)
	if zero != 1 || features[5].Contribution == nil || *features[5].Contribution != 0 {
		t.Fatal("zero tratado como ausência")
	}
	_, _, confidence, features = ScoreFeatures(values, 0.8)
	if confidence != "low" || *features[6].Contribution != -24 {
		t.Fatal("penalidade incorreta")
	}
}
