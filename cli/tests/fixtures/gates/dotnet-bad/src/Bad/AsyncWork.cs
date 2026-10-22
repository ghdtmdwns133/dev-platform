namespace Bad;

public static class AsyncWork
{
    // CA2007: missing ConfigureAwait(false) in a library.
    public static async Task<int> RunAsync()
    {
        await Task.Delay(1);
        return 1;
    }
}
