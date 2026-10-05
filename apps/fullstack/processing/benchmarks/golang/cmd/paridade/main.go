// Comando paridade executa o motor Go sobre um documento portátil de benchmark.
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"runtime"

	motor "argus/benchmark/motor"
)

func executar() error {
	input := flag.String("input", "", "JSON de casos, ciclo ou cargas")
	catalogs := flag.String("catalogs", "../../src/argus_processing/catalogs", "Pasta dos cinco catálogos Python")
	flag.Parse()
	if *input == "" {
		return fmt.Errorf("informe -input")
	}
	runtime.GOMAXPROCS(1)
	catalog, err := motor.CarregarCatalogo(*catalogs)
	if err != nil {
		return err
	}
	document, err := motor.LerDocumento(*input, catalog)
	if err != nil {
		return err
	}
	result, err := motor.ExecutarDocumento(document, catalog)
	if err != nil {
		return err
	}
	encoder := json.NewEncoder(os.Stdout)
	encoder.SetEscapeHTML(false)
	return encoder.Encode(result)
}
func main() {
	if err := executar(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
