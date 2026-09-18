def fibonacci(n: int) -> list[int]:
    """
    Menghasilkan deret Fibonacci hingga n bilangan pertama.
    
    Args:
        n: Jumlah bilangan Fibonacci yang diinginkan (n >= 0)
    
    Returns:
        List berisi n bilangan Fibonacci pertama
    """
    if n <= 0:
        return []
    elif n == 1:
        return [0]
    elif n == 2:
        return [0, 1]
    
    deret = [0, 1]
    for _ in range(2, n):
        deret.append(deret[-1] + deret[-2])
    
    return deret


def fibonacci_n(n: int) -> int:
    """
    Menghitung bilangan Fibonacci ke-n (0-indexed).
    
    Args:
        n: Indeks bilangan Fibonacci (n >= 0)
    
    Returns:
        Bilangan Fibonacci ke-n
    """
    if n <= 0:
        return 0
    elif n == 1:
        return 1
    
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    
    return b


if __name__ == "__main__":
    # Contoh penggunaan
    print("Deret Fibonacci 10 bilangan pertama:", fibonacci(10))
    print("Bilangan Fibonacci ke-10:", fibonacci_n(10))