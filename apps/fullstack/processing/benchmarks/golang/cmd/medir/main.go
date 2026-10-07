// Comando medir cronometra o cálculo puro em um processo isolado por carga.
package main

import (
	"bufio"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"runtime"

	motor "argus/benchmark/motor"
)

func medir(fn func() any, warmups, repetitions int) []int64 {
	for i := 0; i < warmups; i++ {
		runtime.KeepAlive(fn())
	}
	samples := make([]int64, 0, repetitions)
	for i := 0; i < repetitions; i++ {
		start := clockTick()
		result := fn()
		elapsed := elapsedNS(start, clockTick())
		samples = append(samples, elapsed)
		runtime.KeepAlive(result)
	}
	return samples
}

func executar(input, catalogs string, warmups, repetitions int) (map[string]any, error) {
	catalog, err := motor.CarregarCatalogo(catalogs)
	if err != nil {
		return nil, err
	}
	doc, err := motor.LerDocumento(input, catalog)
	if err != nil {
		return nil, err
	}
	if doc.Case == nil {
		return nil, fmt.Errorf("esperado um único ciclo em case")
	}
	c := *doc.Case
	baselines := c.EstadoInicial()
	qualityStage := func() []motor.SourceQuality {
		return motor.EvaluateQuality(c.Facts, catalog, c.WindowStart, c.WindowEnd, c.SimulatorEnd)
	}
	quality := qualityStage()
	anomalies, _ := motor.Detect(c.Facts, baselines, catalog, motor.DetectorPadrao())
	candidates := motor.BuildCandidates(anomalies, c.Facts, quality, catalog)
	score := func(candidates []motor.Candidate, anomalies []motor.Anomaly, quality []motor.SourceQuality) motor.ResultadoRegras {
		r, err := motor.EvaluateCandidates(candidates, anomalies, quality, catalog, motor.LimitesPadrao())
		if err != nil {
			panic(err)
		}
		return r
	}
	stages := []struct {
		name string
		fn   func() any
	}{
		{"quality", func() any { return qualityStage() }},
		{"detector", func() any {
			a, b := motor.Detect(c.Facts, baselines, catalog, motor.DetectorPadrao())
			return struct {
				Anomalies []motor.Anomaly
				Baselines map[motor.ChaveBaseline]motor.Baseline
			}{a, b}
		}},
		{"candidates", func() any { return motor.BuildCandidates(anomalies, c.Facts, quality, catalog) }},
		{"scoring", func() any { return score(candidates, anomalies, quality) }},
		{"total", func() any {
			q := qualityStage()
			a, b := motor.Detect(c.Facts, baselines, catalog, motor.DetectorPadrao())
			candidates := motor.BuildCandidates(a, c.Facts, q, catalog)
			r := score(candidates, a, q)
			return struct {
				Quality   []motor.SourceQuality
				Anomalies []motor.Anomaly
				Baselines map[motor.ChaveBaseline]motor.Baseline
				Rules     motor.ResultadoRegras
			}{q, a, b, r}
		}},
	}
	samples := map[string][]int64{}
	for _, stage := range stages {
		samples[stage.name] = medir(stage.fn, warmups, repetitions)
	}
	return map[string]any{
		"runtime": runtime.Version(), "gomaxprocs": runtime.GOMAXPROCS(0),
		"samples_ns": samples, "clock": clockName, "clock_resolution_ns": clockResolutionNS,
	}, nil
}

func main() {
	input := flag.String("input", "", "JSON de um ciclo")
	catalogs := flag.String("catalogs", "../../src/argus_processing/catalogs", "Pasta dos catálogos")
	warmups := flag.Int("warmups", 5, "Aquecimentos por etapa")
	repetitions := flag.Int("repetitions", 50, "Repetições por etapa")
	flag.Parse()
	if *input == "" || *warmups < 3 || *repetitions < 20 {
		fmt.Fprintln(os.Stderr, "Informe -input, ao menos 3 aquecimentos e 20 repetições")
		os.Exit(1)
	}
	runtime.GOMAXPROCS(1)
	scanner := bufio.NewScanner(os.Stdin)
	fmt.Printf("{\"ready\":true,\"pid\":%d}\n", os.Getpid())
	if !scanner.Scan() {
		os.Exit(1)
	}
	result, err := executar(*input, *catalogs, *warmups, *repetitions)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	if err = json.NewEncoder(os.Stdout).Encode(result); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	// O controlador lê PeakWorkingSetSize/VmHWM enquanto o processo ainda existe.
	scanner.Scan()
}
