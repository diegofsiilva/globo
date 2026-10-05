// Onze famílias determinísticas, traduzidas de rules.py.
package motor

import (
	"encoding/json"
	"fmt"
	"math"
	"sort"
	"strings"
	"time"
)

var fontesInternas = map[string]bool{"newrelic": true, "apollo": true, "prometheus": true, "rpaas": true}
var metricasVolume = map[string]bool{"sessions": true, "active_sessions": true, "requests_total": true, "rpm": true, "throughput": true}

func dentro(a, b Instante, minutes int) bool {
	return math.Abs(a.Sub(b.Time).Seconds()) <= float64(minutes*60)
}
func qoe(metric string) bool {
	m := strings.ToLower(metric)
	for _, token := range []string{"jointime", "buffer", "stall", "latency", "dropped"} {
		if strings.Contains(m, token) {
			return true
		}
	}
	return false
}
func erro(metric string) bool {
	m := strings.ToLower(metric)
	return strings.Contains(m, "error") || strings.Contains(m, "4xx") || strings.Contains(m, "5xx")
}
func metricaInterna(metric string) bool {
	return erro(metric) || strings.Contains(metric, "latency") || metric == "apdex" || strings.Contains(metric, "response_time")
}
func qualidade(source string, quality map[string]SourceQuality) *float64 {
	return quality[source].QualityScore
}
func impacto(f *Fact) *float64 {
	if f == nil || f.SampleSize == nil {
		return nil
	}
	return ptr(math.Min(1, math.Log1p(float64(*f.SampleSize))/math.Log1p(10000)))
}
func opcional(s *string) any {
	if s == nil {
		return nil
	}
	return *s
}
func verdadeiro(v any) bool {
	switch v := v.(type) {
	case nil:
		return false
	case bool:
		return v
	case string:
		return v != ""
	case float64:
		return v != 0
	case []any:
		return len(v) > 0
	case map[string]any:
		return len(v) > 0
	default:
		return true
	}
}
func evidencia(role, polarity, explanation string, fact *Fact, observed, expected, strength, quality *float64) Evidence {
	e := Evidence{
		Role: role, Polarity: polarity, Explanation: explanation, Fact: fact,
		Observed: observed, Expected: expected, Strength: strength, Quality: quality,
		Attributes: map[string]any{},
	}
	if fact != nil {
		e.FactKey = &fact.FactKey
		e.VersionLSN = &fact.VersionLSN
	}
	return e
}
func candidato(family string, index *int, subject *Fact, supporting []*Fact, scope map[string]any, title, summary string) Candidate {
	c := Candidate{
		Family: family, Kind: "operational", AnomalyIndex: index, Subject: subject,
		Supporting: supporting, SupportingFactKeys: []string{}, RequiredMissing: []string{},
		Contrary: []Evidence{}, Scope: scope, Title: title, Summary: summary,
		Specificity: ptr(1.0),
	}
	if subject != nil {
		c.SubjectFactKey = &subject.FactKey
	}
	for _, f := range supporting {
		c.SupportingFactKeys = append(c.SupportingFactKeys, f.FactKey)
	}
	return c
}
func relacionados(subject *Fact, facts []*Fact, catalog *Catalog, minutes int, predicate func(*Fact) bool) []*Fact {
	result := []*Fact{}
	for _, f := range facts {
		if f.FactKey != subject.FactKey && dentro(f.EventStart, subject.EventStart, minutes) && catalog.Related(f.Entity, subject.Entity) && predicate(f) {
			result = append(result, f)
		}
	}
	return result
}
func liftSegmento(subject *Fact, peers []*Fact) (*float64, *float64) {
	if len(peers) == 0 || subject.Value == nil {
		return nil, nil
	}
	sum := 0.0
	for _, f := range peers {
		sum += *f.Value
	}
	mean := sum / float64(len(peers))
	var lift *float64
	if mean != 0 {
		lift = ptr(*subject.Value / mean)
	}
	return lift, ptr(*subject.Value - mean)
}
func requisitosSegmento(c *Candidate, subject *Fact, peers []*Fact, minSample int64, description string) {
	lift, delta := liftSegmento(subject, peers)
	if amostra(subject) < minSample {
		c.RequiredMissing = append(c.RequiredMissing, description)
	}
	if lift == nil || *lift < 2 || delta == nil || *delta < 1 {
		c.RequiredMissing = append(c.RequiredMissing, "lift >= 2 e diferença >= 1 pp contra pares")
	}
	value := numero(lift)
	if value == 0 {
		value = 1
	}
	c.Specificity = ptr(math.Min(1, value/3))
}

// BuildCandidates traduz as onze famílias, preservando a ordem das evidências.
func BuildCandidates(anomalies []Anomaly, facts []*Fact, qualities []SourceQuality, catalog *Catalog) []Candidate {
	candidates := []Candidate{}
	anomalous := map[string]bool{}
	for _, a := range anomalies {
		anomalous[a.Fact.FactKey] = true
	}
	for index, anomaly := range anomalies {
		subject := anomaly.Fact
		metric := strings.ToLower(subject.Metric)
		source := subject.Source
		var deploy *Fact
		for _, f := range facts {
			delta := subject.EventStart.Sub(f.EventStart.Time).Seconds()
			if f.Source == "tsuru" && f.Metric == "app.deploy" && delta >= 0 && delta <= 3600 && catalog.Related(f.Entity, subject.Entity) && (deploy == nil || f.EventStart.After(deploy.EventStart.Time)) {
				deploy = f
			}
		}
		if deploy != nil {
			c := candidato("deploy_regression", ptr(index), subject, []*Fact{deploy}, map[string]any{"service": catalog.NormalizeEntity(subject.Entity)}, "Possível regressão após deploy em "+subject.Entity, "A degradação começou depois de um deploy semanticamente relacionado.")
			c.TemporalScore = ptr(math.Pow(2, -subject.EventStart.Sub(deploy.EventStart.Time).Minutes()/15))
			candidates = append(candidates, c)
		}
		if fontesInternas[source] && metricaInterna(metric) {
			support := relacionados(subject, facts, catalog, 15, func(f *Fact) bool { return fontesInternas[f.Source] && metricaInterna(f.Metric) })
			c := candidato("backend_internal", ptr(index), subject, support, map[string]any{"service": catalog.NormalizeEntity(subject.Entity)}, "Possível falha interna em "+subject.Entity, "Sinais internos indicam erro, latência ou queda de saúde do serviço.")
			if source == "rpaas" && strings.Contains(metric, "4xx") {
				c.Contrary = append(c.Contrary, evidencia("subject", "contrary", "4xx de RPaaS isolado pode ser comportamento estrutural", subject, ptr(anomaly.Observed), ptr(anomaly.Expected), ptr(0.9), nil))
			}
			candidates = append(candidates, c)
		}
		author := false
		if source == "npaw_error_attr" {
			attrs, _ := json.Marshal(subject.Attributes)
			author = strings.Contains(strings.ToLower(string(attrs)), "author")
		}
		playback := (source == "rpaas" && strings.Contains(metric, "4xx") && catalog.PlaybackVhost(subject.Entity)) || strings.Contains(metric, "startup_error") || (source == "npaw_error_category" && texto(subject.DimensionValue) == "acesso") || author
		if playback {
			support := relacionados(subject, facts, catalog, 30, func(f *Fact) bool { return erro(f.Metric) })
			c := candidato("playback_authorization", ptr(index), subject, support, map[string]any{"flow": "playback", "entity": subject.Entity}, "Possível falha de playback ou autorização", "Erros de acesso ou inicialização se concentram no fluxo de playback.")
			if (strings.Contains(metric, "rate") || strings.Contains(metric, "4xx")) && amostra(subject) < 100 {
				c.RequiredMissing = append(c.RequiredMissing, "volume mínimo de 100 requisições/sessões")
			}
			candidates = append(candidates, c)
		}
		if strings.HasPrefix(source, "cdn_") || (source == "npaw_error_attr" && verdadeiro(subject.Attributes["cdn"])) {
			support := relacionados(subject, facts, catalog, 30, func(f *Fact) bool { return qoe(f.Metric) })
			c := candidato("cdn_degradation", ptr(index), subject, support, map[string]any{"channel": subject.Entity}, "Possível degradação de CDN", "Erros de entrega aparecem no mesmo canal da degradação observada.")
			for _, a := range anomalies {
				f := a.Fact
				if strings.HasPrefix(f.Source, "origin_") && !f.EventStart.After(subject.EventStart.Time) && dentro(f.EventStart, subject.EventStart, 30) && catalog.Related(f.Entity, subject.Entity) {
					c.Specificity = ptr(0.5)
					break
				}
			}
			candidates = append(candidates, c)
		}
		if strings.HasPrefix(source, "origin_") || (source == "npaw_error_category" && texto(subject.DimensionValue) == "origem") {
			support := relacionados(subject, facts, catalog, 30, func(f *Fact) bool {
				return (strings.HasPrefix(f.Source, "cdn_") || qoe(f.Metric)) && !f.EventStart.Before(subject.EventStart.Time)
			})
			c := candidato("origin_encoding", ptr(index), subject, support, map[string]any{"channel": subject.Entity}, "Possível falha de origem ou encoding", "A origem degradou antes ou junto dos sinais de entrega e experiência.")
			for _, a := range anomalies {
				f := a.Fact
				if f.EventStart.Before(subject.EventStart.Time) && dentro(f.EventStart, subject.EventStart, 30) && catalog.Related(f.Entity, subject.Entity) && (strings.HasPrefix(f.Source, "cdn_") || qoe(f.Metric)) {
					c.Contrary = append(c.Contrary, evidencia("supporting", "contrary", "efeito downstream começou antes da origem", f, ptr(a.Observed), ptr(a.Expected), ptr(0.9), nil))
				}
			}
			candidates = append(candidates, c)
		}
		if source == "npaw_geo" && (texto(subject.DimensionType) == "uf" || texto(subject.DimensionType) == "isp") && subject.DimensionValue != nil && *subject.DimensionValue != "?" && *subject.DimensionValue != "(desconhecido)" {
			peers := []*Fact{}
			for _, f := range facts {
				if f.Source == source && f.Metric == subject.Metric && opcional(f.DimensionType) == opcional(subject.DimensionType) && opcional(f.DimensionValue) != opcional(subject.DimensionValue) && !anomalous[f.FactKey] && dentro(f.EventStart, subject.EventStart, 60) && f.Value != nil {
					peers = append(peers, f)
				}
			}
			c := candidato("regional_or_isp", ptr(index), subject, peers, map[string]any{"dimension_type": opcional(subject.DimensionType), "dimension_value": opcional(subject.DimensionValue)}, "Possível degradação por "+strings.ToUpper(*subject.DimensionType), "A degradação está concentrada em um recorte com volume material.")
			requisitosSegmento(&c, subject, peers, 500, "500 sessões no segmento")
			candidates = append(candidates, c)
		}
		if source == "cloudarmor" && strings.Contains(metric, "blocked") {
			support := relacionados(subject, facts, catalog, 15, func(f *Fact) bool {
				return (erro(f.Metric) || strings.Contains(strings.ToLower(f.Metric), "cpu")) && !f.EventStart.Before(subject.EventStart.Time)
			})
			c := candidato("waf_block", ptr(index), subject, support, map[string]any{"application": catalog.NormalizeEntity(subject.Entity)}, "Possível ataque ou bloqueio de WAF", "O aumento de bloqueios antecede ou coincide com impacto na aplicação.")
			for _, a := range anomalies {
				f := a.Fact
				if f.EventStart.Before(subject.EventStart.Time) && dentro(f.EventStart, subject.EventStart, 15) && catalog.Related(f.Entity, subject.Entity) && (erro(f.Metric) || strings.Contains(strings.ToLower(f.Metric), "cpu")) {
					c.Contrary = append(c.Contrary, evidencia("supporting", "contrary", "impacto começou antes do aumento de bloqueios", f, ptr(a.Observed), ptr(a.Expected), ptr(0.9), nil))
				}
			}
			candidates = append(candidates, c)
		}
		if source == "npaw_player" || source == "npaw_device" || source == "npaw_player_live" {
			peers := []*Fact{}
			for _, f := range facts {
				if f.Source == source && f.Metric == subject.Metric && f.Entity != subject.Entity && !anomalous[f.FactKey] && dentro(f.EventStart, subject.EventStart, 60) && f.Value != nil {
					peers = append(peers, f)
				}
			}
			c := candidato("player_or_device", ptr(index), subject, peers, map[string]any{"dimension_type": opcional(subject.DimensionType), "dimension_value": opcional(subject.DimensionValue)}, "Possível regressão de player ou dispositivo", "O efeito está concentrado em um segmento enquanto os pares permanecem estáveis.")
			requisitosSegmento(&c, subject, peers, 200, "200 sessões no segmento")
			candidates = append(candidates, c)
		}
		if qoe(metric) {
			errorKeys := map[string]bool{}
			for _, a := range anomalies {
				if erro(a.Fact.Metric) {
					errorKeys[a.Fact.FactKey] = true
				}
			}
			support := relacionados(subject, facts, catalog, 60, func(f *Fact) bool { return erro(f.Metric) && !errorKeys[f.FactKey] })
			c := candidato("qoe_without_error", ptr(index), subject, support, map[string]any{"entity": subject.Entity}, "Possível degradação de QoE sem erro explícito", "A experiência piorou sem aumento correspondente das métricas de erro.")
			if len(support) == 0 {
				c.RequiredMissing = append(c.RequiredMissing, "métrica de erro disponível e normal")
			}
			candidates = append(candidates, c)
		}
		if metricasVolume[metric] && anomaly.Direction == "up" {
			events := []*Fact{}
			for _, f := range facts {
				end := f.EventStart
				if f.EventEnd != nil {
					end = *f.EventEnd
				}
				if f.Source == "editorial" && f.Metric == "live_event" && !f.EventStart.After(subject.EventStart.Time) && !subject.EventStart.After(end.Time) && catalog.Related(f.Entity, subject.Entity) {
					events = append(events, f)
				}
			}
			if len(events) > 0 {
				c := candidato("expected_live_peak", ptr(index), subject, events, map[string]any{"channel": subject.Entity}, "Pico esperado por evento ao vivo", "O volume cresceu durante evento compatível sem degradação de experiência.")
				c.Kind = "context"
				for _, a := range anomalies {
					f := a.Fact
					if catalog.Related(f.Entity, subject.Entity) && (erro(f.Metric) || qoe(f.Metric)) && dentro(f.EventStart, subject.EventStart, 60) {
						c.Contrary = append(c.Contrary, evidencia("supporting", "contrary", "experiência também degradou", f, ptr(a.Observed), ptr(a.Expected), ptr(a.Strength), nil))
					}
				}
				if len(c.Contrary) > 0 {
					c.RequiredMissing = append(c.RequiredMissing, "erro e QoE precisam permanecer normais")
				}
				normalError, normalQoe := false, false
				for _, f := range facts {
					if catalog.Related(f.Entity, subject.Entity) && dentro(f.EventStart, subject.EventStart, 60) && !anomalous[f.FactKey] {
						normalError = normalError || erro(f.Metric)
						normalQoe = normalQoe || qoe(f.Metric)
					}
				}
				if !normalError {
					c.RequiredMissing = append(c.RequiredMissing, "métrica de erro disponível e normal")
				}
				if !normalQoe {
					c.RequiredMissing = append(c.RequiredMissing, "métrica de QoE disponível e normal")
				}
				candidates = append(candidates, c)
			}
		}
	}
	for _, q := range qualities {
		if q.Status != "delayed" && q.Status != "incomplete" && q.Status != "silent" && q.Status != "invalid" {
			continue
		}
		c := candidato("source_data_delay", nil, nil, nil, map[string]any{"source": q.Source}, "Possível falha ou atraso da fonte "+q.Source, "O canário classificou a fonte como "+q.Status+"; ausência não será tratada como incidente.")
		c.Kind = "data_quality"
		candidates = append(candidates, c)
	}
	return candidates
}

func corroboracao(facts []*Fact, subject *Fact, anomalies []Anomaly, catalog *Catalog, quality map[string]SourceQuality, minutes int) *float64 {
	byFact := map[string]Anomaly{}
	for _, a := range anomalies {
		byFact[a.Fact.FactKey] = a
	}
	strongest := map[string]float64{}
	groups := []string{}
	for _, f := range facts {
		q := qualidade(f.Source, quality)
		if q == nil {
			continue
		}
		strength := 0.5
		if a, ok := byFact[f.FactKey]; ok {
			strength = a.Strength
		}
		delta := 0.0
		if subject != nil {
			delta = math.Abs(f.EventStart.Sub(subject.EventStart.Time).Seconds()) / 60
		}
		alignment := math.Max(0, 1-delta/float64(max(1, minutes)))
		group := catalog.Source(f.Source).IndependenceGroup
		// A ordem de inserção reproduz o produto dos grupos no dicionário Python.
		if _, ok := strongest[group]; !ok {
			groups = append(groups, group)
		}
		strongest[group] = math.Max(strongest[group], strength*alignment*(*q))
	}
	if len(groups) == 0 {
		return nil
	}
	product := 1.0
	for _, g := range groups {
		product *= 1 - strongest[g]
	}
	return ptr(1 - product)
}

type Limites struct{ MaxTotal, MaxPerFamily, MaxGenerated int }

func LimitesPadrao() Limites { return Limites{10000, 2000, 500} }

// EvaluateCandidates preserva cortes, score, evidências, hashes e deduplicação.
func EvaluateCandidates(candidates []Candidate, anomalies []Anomaly, qualities []SourceQuality, catalog *Catalog, limits Limites) (ResultadoRegras, error) {
	result := ResultadoRegras{Candidates: candidates, Hypotheses: []Hypothesis{}, CandidatesPrefiltered: len(candidates)}
	quality := map[string]SourceQuality{}
	for _, q := range qualities {
		quality[q.Source] = q
	}
	type ordenado struct {
		c                Candidate
		strength, impact float64
		hash             string
	}
	ordered := make([]ordenado, 0, len(candidates))
	for _, c := range candidates {
		strength := 1.0
		if c.AnomalyIndex != nil {
			strength = anomalies[*c.AnomalyIndex].Strength
		}
		support := append([]string{}, c.SupportingFactKeys...)
		sort.Strings(support)
		hash := CanonicalHash(map[string]any{"family": c.Family, "scope": c.Scope, "subject": opcional(c.SubjectFactKey), "supporting": support})
		ordered = append(ordered, ordenado{c, strength, numero(impacto(c.Subject)), hash})
	}
	sort.SliceStable(ordered, func(i, j int) bool {
		a, b := ordered[i], ordered[j]
		if a.strength != b.strength {
			return a.strength > b.strength
		}
		if a.impact != b.impact {
			return a.impact > b.impact
		}
		if a.c.Family != b.c.Family {
			return a.c.Family < b.c.Family
		}
		return a.hash < b.hash
	})
	selected := []Candidate{}
	perFamily := map[string]int{}
	for _, item := range ordered {
		c := item.c
		if len(selected) >= limits.MaxTotal || perFamily[c.Family] >= limits.MaxPerFamily {
			result.CandidatesTruncated++
			continue
		}
		selected = append(selected, c)
		perFamily[c.Family]++
	}
	result.CandidatesEvaluated = len(selected)
	generated := 0
	seen := map[string]bool{}
	for _, c := range selected {
		var anomaly *Anomaly
		if c.AnomalyIndex != nil {
			anomaly = &anomalies[*c.AnomalyIndex]
		}
		subject := c.Subject
		var sourceQ *float64
		if subject != nil {
			sourceQ = qualidade(subject.Source, quality)
		} else if source, ok := c.Scope["source"].(string); ok {
			sourceQ = qualidade(source, quality)
		}
		rule, ok := catalog.Rules[c.Family]
		if !ok {
			return result, fmt.Errorf("família ausente no catálogo: %s", c.Family)
		}
		corrob := corroboracao(c.Supporting, subject, anomalies, catalog, quality, rule.WindowMinutes)
		contradiction := 0.0
		for _, e := range c.Contrary {
			contradiction = math.Max(contradiction, numero(e.Strength))
		}
		values := map[string]ValorFeature{
			"A": {"available", ptr(1 - numero(sourceQ)), "severidade do canário"},
			"T": {"not_applicable", nil, "família sem evento causal identificável"},
			"C": {"unavailable", nil, "nenhuma fonte independente disponível"},
			"E": {"available", c.Specificity, "especificidade semântica do escopo"},
			"I": {"unavailable", nil, "volume afetado indisponível"},
			"Q": {"unavailable", nil, "canário indisponível"},
		}
		if anomaly != nil {
			values["A"] = ValorFeature{"available", ptr(anomaly.Strength), "força do desvio causal"}
		}
		if c.TemporalScore != nil {
			values["T"] = ValorFeature{"available", c.TemporalScore, "proximidade da causa"}
		}
		if corrob != nil {
			values["C"] = ValorFeature{"available", corrob, "fontes independentes relacionadas"}
		}
		if v := impacto(subject); v != nil {
			values["I"] = ValorFeature{"available", v, "volume afetado"}
		}
		if sourceQ != nil {
			values["Q"] = ValorFeature{"available", sourceQ, "qualidade da fonte subject"}
		}
		score, coverage, confidence, features := ScoreFeatures(values, contradiction)
		status := "discarded"
		if contradiction >= 0.80 {
			status = "discarded"
		} else if len(c.RequiredMissing) > 0 {
			status = "insufficient_evidence"
		} else if score >= 40 && coverage >= 0.50 && generated < limits.MaxGenerated {
			status = "generated"
			generated++
		} else if score >= 40 && coverage >= 0.50 {
			result.CandidatesTruncated++
		}
		evidence := []Evidence{}
		if anomaly != nil && subject != nil {
			evidence = append(evidence, evidencia("subject", "favorable", "anomalia que iniciou a avaliação", subject, ptr(anomaly.Observed), ptr(anomaly.Expected), ptr(anomaly.Strength), sourceQ))
		}
		for _, f := range c.Supporting {
			evidence = append(evidence, evidencia("supporting", "favorable", "fato temporal e semanticamente relacionado", f, f.Value, nil, ptr(0.7), qualidade(f.Source, quality)))
		}
		evidence = append(evidence, c.Contrary...)
		for _, missing := range c.RequiredMissing {
			evidence = append(evidence, evidencia("required", "missing", missing, nil, nil, nil, nil, nil))
		}
		var start Instante
		if subject != nil {
			start = subject.EventStart
		} else {
			source, ok := c.Scope["source"].(string)
			if !ok {
				return result, fmt.Errorf("fonte ausente no escopo")
			}
			q, ok := quality[source]
			if !ok {
				return result, fmt.Errorf("qualidade ausente: %s", source)
			}
			if q.LastObservationAt != nil {
				start = *q.LastObservationAt
			} else {
				at, ok := q.Details["evaluated_at"].(string)
				if !ok {
					return result, fmt.Errorf("evaluated_at ausente: %s", source)
				}
				t, err := time.Parse(time.RFC3339Nano, at)
				if err != nil {
					return result, err
				}
				start = Instante{t}
			}
		}
		end := start
		if subject != nil && subject.EventEnd != nil {
			end = *subject.EventEnd
		}
		period := Instante{time.Date(start.Year(), start.Month(), start.Day(), start.Hour(), start.Minute(), 0, 0, start.Location())}
		identity := map[string]any{"family": c.Family, "scope": c.Scope, "period": period.ISO()}
		lineage := CanonicalHash(identity)
		factIDs := []string{}
		for _, e := range evidence {
			if e.Fact != nil {
				factIDs = append(factIDs, fmt.Sprintf("%s:%d", e.Fact.FactKey, e.Fact.VersionLSN))
			}
		}
		sort.Strings(factIDs)
		identity["facts"] = factIDs
		dedup := CanonicalHash(identity)
		indexes := []int{}
		if c.AnomalyIndex != nil {
			indexes = append(indexes, *c.AnomalyIndex)
		}
		supporting := map[string]bool{}
		for _, f := range c.Supporting {
			supporting[f.FactKey] = true
		}
		for i, a := range anomalies {
			if supporting[a.Fact.FactKey] && (c.AnomalyIndex == nil || i != *c.AnomalyIndex) {
				indexes = append(indexes, i)
			}
		}
		// Como no Python, a cota de geradas é consumida antes da deduplicação final.
		if seen[dedup] {
			continue
		}
		seen[dedup] = true
		result.Hypotheses = append(result.Hypotheses, Hypothesis{
			Family: c.Family, Kind: c.Kind, Title: c.Title, Summary: c.Summary, Scope: c.Scope,
			EffectStart: start, EffectEnd: end, Score: score, Coverage: coverage,
			Confidence: confidence, EvaluationStatus: status, ContradictionStrength: contradiction,
			DedupKey: dedup, LineageKey: lineage, Features: features, Evidence: evidence,
			AnomalyIndexes: indexes,
		})
	}
	return result, nil
}
