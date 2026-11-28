using System.IO;
using YYBToolbox.WinUI.Models;

namespace YYBToolbox.WinUI.Services;

public class AppState
{
    public static AppState Current { get; } = new();

    public ConfigService Config { get; }
    public AdbClient Adb { get; private set; }
    public DeviceInfo? Info { get; set; }
    public IntPtr WindowHandle { get; set; }

    public event Action<string>? StatusChanged;

    private AppState()
    {
        Config = ConfigService.Load();
        Adb = new AdbClient(AdbClient.Autodetect(Config.AdbPath), Config.Serial);
    }

    public void SetStatus(string text) => StatusChanged?.Invoke(text);

    public static void Log(object? content)
    {
        try
        {
            var file = Path.Combine(AppContext.BaseDirectory, "startup.log");
            File.AppendAllText(file, $"[{DateTime.Now:HH:mm:ss}] {content}\n");
        }
        catch { }
    }

    public void RefreshAdb()
    {
        Adb = new AdbClient(AdbClient.Autodetect(Config.AdbPath), Config.Serial);
    }

    public async Task<string> ConnectAsync()
    {
        return await Task.Run(() => Adb.EnsureConnected(Config.Serial, retries: 3, waitSec: 4));
    }

    public async Task<DeviceInfo> CollectInfoAsync()
    {
        return await Task.Run(() => DeviceInfoCollector.Collect(Adb));
    }
}
