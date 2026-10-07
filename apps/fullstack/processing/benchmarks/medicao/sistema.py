"""Afinidade de CPU e pico residente do processo, sem dependências externas."""

from __future__ import annotations

import ctypes
import os
import platform
from pathlib import Path


def _kernel32():
    """Declara assinaturas de handles com tamanho correto no Windows de 64 bits."""
    from ctypes import wintypes

    library = ctypes.WinDLL("kernel32", use_last_error=True)
    library.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    library.OpenProcess.restype = wintypes.HANDLE
    library.CloseHandle.argtypes = [wintypes.HANDLE]
    library.CloseHandle.restype = wintypes.BOOL
    return library


def cpu_disponivel() -> int:
    """Escolhe a primeira CPU permitida ao controlador, sem mudar sua afinidade."""
    if os.name != "nt":
        return min(os.sched_getaffinity(0))
    from ctypes import wintypes

    library = _kernel32()
    library.GetProcessAffinityMask.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.POINTER(ctypes.c_size_t),
    ]
    library.GetProcessAffinityMask.restype = wintypes.BOOL
    handle = library.OpenProcess(0x0400, False, os.getpid())
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        process_mask, system_mask = ctypes.c_size_t(), ctypes.c_size_t()
        if not library.GetProcessAffinityMask(
            handle, ctypes.byref(process_mask), ctypes.byref(system_mask)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        mask = process_mask.value
        return (mask & -mask).bit_length() - 1
    finally:
        library.CloseHandle(handle)


def fixar_cpu(pid: int, cpu: int) -> None:
    """Aplica a mesma CPU apenas ao filho que será medido."""
    if os.name != "nt":
        os.sched_setaffinity(pid, {cpu})
        return
    from ctypes import wintypes

    library = _kernel32()
    library.SetProcessAffinityMask.argtypes = [wintypes.HANDLE, ctypes.c_size_t]
    library.SetProcessAffinityMask.restype = wintypes.BOOL
    handle = library.OpenProcess(0x0200, False, pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if not library.SetProcessAffinityMask(handle, 1 << cpu):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        library.CloseHandle(handle)


def pico_rss(pid: int) -> int:
    """Lê o pico residente desde o início do filho, em bytes, antes de sua saída."""
    if os.name != "nt":
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmHWM:"):
                return int(line.split()[1]) * 1024
        raise RuntimeError("VmHWM indisponível")
    from ctypes import wintypes

    class ProcessMemoryCounters(ctypes.Structure):
        """Layout oficial de PROCESS_MEMORY_COUNTERS, incluindo campos não utilizados."""

        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (name, ctypes.c_size_t)
            for name in (
                "PeakWorkingSetSize",
                "WorkingSetSize",
                "QuotaPeakPagedPoolUsage",
                "QuotaPagedPoolUsage",
                "QuotaPeakNonPagedPoolUsage",
                "QuotaNonPagedPoolUsage",
                "PagefileUsage",
                "PeakPagefileUsage",
            )
        ]

    library = _kernel32()
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(ProcessMemoryCounters),
        wintypes.DWORD,
    ]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    handle = library.OpenProcess(0x0400, False, pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return counters.PeakWorkingSetSize
    finally:
        library.CloseHandle(handle)


def ambiente() -> dict:
    """Registra hardware e sistema, sem nomes de usuário, host ou variáveis secretas."""
    result = {
        "os": platform.system(),
        "os_release": platform.release(),
        "os_version": platform.version(),
        "architecture": platform.machine(),
        "logical_cpus": os.cpu_count(),
        "cpu": platform.processor(),
    }
    if os.name == "nt":
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
        ) as key:
            result["cpu"] = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()

        class MemoryStatus(ctypes.Structure):
            """Layout de MEMORYSTATUSEX para consultar memória física instalada."""

            _fields_ = [("length", ctypes.c_uint32), ("load", ctypes.c_uint32)] + [
                (name, ctypes.c_uint64)
                for name in (
                    "total",
                    "available",
                    "total_page",
                    "available_page",
                    "total_virtual",
                    "available_virtual",
                    "extended",
                )
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        library = _kernel32()
        library.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(MemoryStatus)]
        library.GlobalMemoryStatusEx.restype = ctypes.c_int
        if not library.GlobalMemoryStatusEx(ctypes.byref(status)):
            raise ctypes.WinError(ctypes.get_last_error())
        result["physical_memory_bytes"] = status.total
    else:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                result["physical_memory_bytes"] = int(line.split()[1]) * 1024
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                result["cpu"] = line.split(":", 1)[1].strip()
                break
    return result
