// Canário determinístico de qualidade, traduzido de quality.py.
package motor

import (
	"math"
	"sort"
)

func clamp(v float64) float64 { return math.Max(0, math.Min(1, v)) }

// EvaluateQuality inclui fontes silenciosas e usa available_at para freshness.
func EvaluateQuality(facts []*Fact, catalog *Catalog, start, end Instante, simulatorEnd *Instante) []SourceQuality {
	bySource := map[string][]*Fact{}
	names := map[string]bool{}
	for name := range catalog.Sources {
		if name != "default" {
			names[name] = true
		}
	}
	for _, f := range facts {
		if f.Kind == "metric" && (f.Role == "subject" || f.Role == "quality") {
			bySource[f.Source] = append(bySource[f.Source], f)
			names[f.Source] = true
		}
	}
	effectiveEnd := end
	if simulatorEnd != nil && simulatorEnd.Before(end.Time) {
		effectiveEnd = *simulatorEnd
	}
	ordered := make([]string, 0, len(names))
	for name := range names {
		ordered = append(ordered, name)
	}
	sort.Strings(ordered)
	result := make([]SourceQuality, 0, len(ordered))
	for _, source := range ordered {
		cadence := catalog.Source(source).CadenceSeconds
		rows := bySource[source]
		subjects := []*Fact{}
		buckets := map[int64]bool{}
		var last, lastAvailable *Instante
		for _, f := range rows {
			if f.Role == "subject" {
				subjects = append(subjects, f)
				buckets[f.EventStart.UnixMicro()] = true
			}
			if last == nil || f.EventStart.After(last.Time) {
				last = &f.EventStart
			}
			if lastAvailable == nil || f.AvailableAt.After(lastAvailable.Time) {
				lastAvailable = &f.AvailableAt
			}
		}
		expected := int(math.Max(0, math.Floor(effectiveEnd.Sub(start.Time).Seconds()/float64(cadence))))
		observed := len(buckets)
		freshness := 0.0
		status := "unknown"
		var gap *float64
		if lastAvailable == nil {
			if expected > 0 {
				status = "silent"
			}
		} else {
			gap = ptr(math.Max(0, effectiveEnd.Sub(lastAvailable.Time).Seconds()/float64(cadence)))
			freshness = clamp(1 - math.Max(0, *gap-1)/2)
			status = "healthy"
			if *gap > 3 {
				status = "silent"
			} else if *gap > 1.5 {
				status = "delayed"
			}
		}
		completeness := 1.0
		if expected > 0 {
			completeness = clamp(float64(observed) / float64(expected))
		}
		assessed := subjects
		if len(assessed) == 0 {
			assessed = rows
		}
		validity, consistency := 0.0, 0.0
		for _, f := range assessed {
			if f.Value != nil && !math.IsNaN(*f.Value) && !math.IsInf(*f.Value, 0) {
				validity++
				if f.SampleSize == nil || *f.SampleSize >= 0 {
					consistency++
				}
			}
		}
		if len(assessed) > 0 {
			validity /= float64(len(assessed))
			consistency /= float64(len(assessed))
		}
		score := 0.35*freshness + 0.35*completeness + 0.15*validity + 0.15*consistency
		if len(assessed) > 0 && (validity < 0.99 || consistency < 0.99) {
			status = "invalid"
		} else if expected > 0 && len(rows) > 0 && (completeness < 0.70 || (completeness < 0.95 && status == "healthy")) {
			status = "incomplete"
		}
		var available any
		if lastAvailable != nil {
			available = lastAvailable.ISO()
		}
		result = append(result, SourceQuality{
			Source: source, ExpectedCadenceSeconds: cadence, LastObservationAt: last,
			Freshness: ptr(freshness), Completeness: ptr(completeness),
			Validity: ptr(validity), Consistency: ptr(consistency), QualityScore: ptr(score),
			Status: status, ExpectedBuckets: expected, ObservedBuckets: observed,
			Details: map[string]any{
				"gap_cadences": gap, "last_available_at": available,
				"evaluated_at": effectiveEnd.ISO(),
			},
		})
	}
	return result
}
