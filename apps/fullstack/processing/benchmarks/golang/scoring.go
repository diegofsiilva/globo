// Score, cobertura e confiança, traduzidos de scoring.py.
package motor

import "math"

type ValorFeature struct {
	Applicability string
	Value         *float64
	Explanation   string
}

var pesos = []struct {
	Name   string
	Weight float64
}{{"A", 0.25}, {"T", 0.20}, {"C", 0.20}, {"E", 0.15}, {"I", 0.15}, {"Q", 0.05}}

// ScoreFeatures mantém a ordem e distingue ausência, zero e não aplicabilidade.
func ScoreFeatures(values map[string]ValorFeature, contradiction float64) (float64, float64, string, []Feature) {
	availableWeight, applicableWeight, weighted := 0.0, 0.0, 0.0
	features := make([]Feature, 0, 7)
	for _, p := range pesos {
		v, ok := values[p.Name]
		if !ok {
			v = ValorFeature{"unavailable", nil, "feature aplicavel indisponivel"}
		}
		if v.Applicability != "not_applicable" {
			applicableWeight += p.Weight
		}
		var contribution *float64
		if v.Applicability == "available" && v.Value != nil {
			normalized := clamp(*v.Value)
			availableWeight += p.Weight
			weighted += p.Weight * normalized
			contribution = ptr(p.Weight * normalized)
			v.Value = ptr(normalized)
		}
		features = append(features, Feature{p.Name, v.Applicability, v.Value, p.Weight, contribution, v.Explanation})
	}
	base := 0.0
	if availableWeight != 0 {
		base = 100 * weighted / availableWeight
	}
	score := math.Max(0, math.Min(100, base-30*contradiction))
	coverage := 1.0
	if applicableWeight != 0 {
		coverage = availableWeight / applicableWeight
	}
	confidence := "low"
	if score >= 80 && coverage >= 0.80 && numero(values["Q"].Value) >= 0.70 && contradiction < 0.5 {
		confidence = "high"
	} else if score >= 60 && coverage >= 0.60 && contradiction < 0.8 {
		confidence = "medium"
	}
	features = append(features, Feature{"X", "available", ptr(contradiction), 0, ptr(-30 * contradiction), "forca maxima das evidencias contrarias"})
	return score, coverage, confidence, features
}
