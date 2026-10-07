// Detector EWMA estritamente causal, traduzido de detector.py.
package motor

import (
	"math"
	"sort"
	"time"
	_ "time/tzdata" // A zona precisa funcionar também em Windows sem banco IANA instalado.
)

var zonaBRT = func() *time.Location {
	z, err := time.LoadLocation("America/Sao_Paulo")
	if err != nil {
		panic(err)
	}
	return z
}()

type ParametrosDetector struct {
	Alpha      float64
	MinSamples int
	ZThreshold float64
}

func DetectorPadrao() ParametrosDetector { return ParametrosDetector{0.20, 12, 3.5} }

// Detect copia o estado e avalia apenas fatos posteriores ao baseline causal.
func Detect(facts []*Fact, baselines map[ChaveBaseline]Baseline, catalog *Catalog, p ParametrosDetector) ([]Anomaly, map[ChaveBaseline]Baseline) {
	state := make(map[ChaveBaseline]Baseline, len(baselines))
	for k, v := range baselines {
		state[k] = v
	}
	subjects := []*Fact{}
	for _, f := range facts {
		if f.Role == "subject" && f.Kind == "metric" {
			subjects = append(subjects, f)
		}
	}
	sort.SliceStable(subjects, func(i, j int) bool {
		a, b := subjects[i], subjects[j]
		if !a.EventStart.Equal(b.EventStart.Time) {
			return a.EventStart.Before(b.EventStart.Time)
		}
		for _, pair := range [][2]string{{a.Source, b.Source}, {a.Entity, b.Entity}, {a.Metric, b.Metric}, {a.FactKey, b.FactKey}} {
			if pair[0] != pair[1] {
				return pair[0] < pair[1]
			}
		}
		return false
	})
	anomalies := []Anomaly{}
	for _, f := range subjects {
		if f.Value == nil || math.IsNaN(*f.Value) || math.IsInf(*f.Value, 0) {
			continue
		}
		policy := catalog.Metric(f.Metric)
		if policy == nil {
			continue
		}
		key := ChaveBaseline{f.Source, f.Entity, f.Metric, f.EventStart.In(zonaBRT).Hour()}
		baseline := state[key]
		if baseline.LastEventAt != nil && !f.EventStart.After(baseline.LastEventAt.Time) {
			continue
		}
		transformed := *f.Value
		if policy.Transform == "log1p" {
			transformed = math.Log1p(math.Max(*f.Value, 0))
		}
		oldMean, oldVariance := baseline.Mean, baseline.Variance
		if oldMean != nil && baseline.N >= p.MinSamples {
			sigma := math.Max(math.Max(math.Sqrt(math.Max(numero(oldVariance), 0)), policy.SigmaFloor), 0.05*math.Abs(*oldMean))
			z := (transformed - *oldMean) / sigma
			expected := *oldMean
			if policy.Transform == "log1p" {
				expected = math.Expm1(*oldMean)
			}
			bad := *f.Value != expected
			if policy.Direction == "up" {
				bad = *f.Value > expected
			} else if policy.Direction == "down" {
				bad = *f.Value < expected
			}
			absolute := math.Abs(*f.Value - expected)
			relative := absolute / math.Max(math.Abs(expected), 1e-12)
			if math.Abs(z) >= p.ZThreshold && bad && absolute >= policy.MaterialityAbsolute && relative >= policy.MaterialityRelative {
				direction := policy.Direction
				if direction == "two_sided" {
					direction = "down"
					if *f.Value > expected {
						direction = "up"
					}
				}
				anomalies = append(anomalies, Anomaly{
					Fact: f, FactKey: f.FactKey, Observed: *f.Value, Expected: expected,
					Direction: direction, Deviation: *f.Value - expected, Z: z,
					Strength: math.Min(math.Abs(z)/6, 1),
					BaselineSnapshot: map[string]any{
						"mean_transformed": oldMean, "variance_transformed": oldVariance,
						"n": baseline.N, "transform": policy.Transform, "sigma_effective": sigma,
					},
				})
			}
		}
		if oldMean == nil {
			baseline.Mean = ptr(transformed)
			baseline.Variance = ptr(0.0)
		} else {
			delta := transformed - *oldMean
			baseline.Mean = ptr((1-p.Alpha)*(*oldMean) + p.Alpha*transformed)
			baseline.Variance = ptr((1 - p.Alpha) * (numero(oldVariance) + p.Alpha*delta*delta))
		}
		baseline.N++
		baseline.LastEventAt = &f.EventStart
		state[key] = baseline
	}
	return anomalies, state
}
