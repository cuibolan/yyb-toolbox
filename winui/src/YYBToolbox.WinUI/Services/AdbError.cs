namespace YYBToolbox.WinUI.Services;

public class AdbError : Exception
{
    public AdbError(string message) : base(message) { }
}
