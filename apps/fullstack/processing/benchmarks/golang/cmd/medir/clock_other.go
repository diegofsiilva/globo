//go:build !windows

// Nas demais plataformas, o relógio monotônico de time fornece os intervalos.
package main

import "time"

var clockOrigin = time.Now()

const clockName = "Go monotonic time.Since"
const clockResolutionNS = 1

func clockTick() int64                 { return time.Since(clockOrigin).Nanoseconds() }
func elapsedNS(start, end int64) int64 { return end - start }
