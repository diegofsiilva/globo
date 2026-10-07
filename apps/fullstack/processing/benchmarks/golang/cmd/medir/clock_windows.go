// O relógio padrão do Go observado no Windows tinha granularidade de ~0,5 ms.
// QPC também é a base de perf_counter no CPython deste ambiente.
package main

import (
	"syscall"
	"unsafe"
)

var kernel = syscall.NewLazyDLL("kernel32.dll")
var queryCounter = kernel.NewProc("QueryPerformanceCounter")
var clockFrequency = func() int64 {
	var value int64
	ok, _, err := kernel.NewProc("QueryPerformanceFrequency").Call(uintptr(unsafe.Pointer(&value)))
	if ok == 0 || value <= 0 {
		panic(err)
	}
	return value
}()
var clockResolutionNS = 1e9 / float64(clockFrequency)

const clockName = "Windows QueryPerformanceCounter"

func clockTick() int64 {
	var value int64
	ok, _, err := queryCounter.Call(uintptr(unsafe.Pointer(&value)))
	if ok == 0 {
		panic(err)
	}
	return value
}

func elapsedNS(start, end int64) int64 {
	return int64(float64(end-start) * 1e9 / float64(clockFrequency))
}
