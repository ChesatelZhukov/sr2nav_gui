#!/usr/bin/env python3
"""
Прямой тест запуска SR2Nav.exe без GUI
"""
import asyncio
import subprocess
import sys
from pathlib import Path

async def test_direct():
    print("="*80)
    print("🔍 ПРЯМОЙ ТЕСТ ЗАПУСКА SR2Nav.exe")
    print("="*80)
    
    # Путь к SR2Nav.exe
    sr2nav_path = Path("C:/SR2NAV/SR2Nav.exe")  # УКАЖИТЕ ВАШ ПУТЬ!
    
    if not sr2nav_path.exists():
        print(f"❌ Файл не найден: {sr2nav_path}")
        return
    
    print(f"✅ Файл найден: {sr2nav_path}")
    print(f"📁 Рабочая директория: {sr2nav_path.parent}")
    
    # ТЕСТ 1: subprocess.run (синхронный)
    print("\n" + "-"*40)
    print("ТЕСТ 1: subprocess.run (без Enter)")
    print("-"*40)
    
    try:
        result = subprocess.run(
            [str(sr2nav_path)],
            cwd=str(sr2nav_path.parent),
            capture_output=True,
            text=True,
            timeout=5
        )
        print(f"Код возврата: {result.returncode}")
        print(f"stdout: {result.stdout[:200]}...")
        print(f"stderr: {result.stderr[:200]}...")
    except subprocess.TimeoutExpired:
        print("⏰ Таймаут!")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    
    # ТЕСТ 2: asyncio.create_subprocess_exec (без Enter)
    print("\n" + "-"*40)
    print("ТЕСТ 2: asyncio.create_subprocess_exec (без Enter)")
    print("-"*40)
    
    try:
        process = await asyncio.create_subprocess_exec(
            str(sr2nav_path),
            cwd=str(sr2nav_path.parent),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        print(f"PID: {process.pid}")
        
        # Ждем 3 секунды
        await asyncio.sleep(3)
        
        # Завершаем
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=2)
            print(f"✅ Завершён, код: {process.returncode}")
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            print(f"⚠️ Принудительно завершён")
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    
    # ТЕСТ 3: asyncio.create_subprocess_exec (с Enter)
    print("\n" + "-"*40)
    print("ТЕСТ 3: asyncio.create_subprocess_exec (с Enter через 1с)")
    print("-"*40)
    
    try:
        process = await asyncio.create_subprocess_exec(
            str(sr2nav_path),
            cwd=str(sr2nav_path.parent),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        print(f"PID: {process.pid}")
        
        # Отправка Enter через 1 секунду
        await asyncio.sleep(1)
        print("📨 Отправка Enter...")
        process.stdin.write(b'\n')
        await process.stdin.drain()
        
        # Ждем завершения
        try:
            return_code = await asyncio.wait_for(process.wait(), timeout=30)
            print(f"✅ Завершён, код: {return_code}")
        except asyncio.TimeoutError:
            print("⏰ Таймаут! Процесс всё ещё работает")
            process.terminate()
            await asyncio.sleep(1)
            if process.returncode is None:
                process.kill()
                await process.wait()
            print(f"⚠️ Принудительно завершён")
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    
    print("\n" + "="*80)
    print("✅ ТЕСТ ЗАВЕРШЕН")
    print("="*80)

if __name__ == "__main__":
    asyncio.run(test_direct())