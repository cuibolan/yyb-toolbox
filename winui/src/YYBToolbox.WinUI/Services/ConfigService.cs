using System.IO;
using System.Text.Json;

namespace YYBToolbox.WinUI.Services;

public class ConfigService
{
    public string AdbPath { get; set; } = "";
    public string Serial { get; set; } = "127.0.0.1:5555";
    public string Geometry { get; set; } = "1280x820";
    public bool MicrogUninstallConflict { get; set; } = true;
    public bool MicrogGrant { get; set; } = true;
    public bool MicrogFakegapps { get; set; } = true;

    private static readonly string AppDir = AppContext.BaseDirectory;
    private static readonly string ConfigFile = Path.Combine(AppDir, "config.json");

    public static string AppDirectory => AppDir;
    public static string CacheDir => Path.Combine(AppDir, "cache");
    public static string ShotDir => Path.Combine(AppDir, "screenshots");
    public static string ToolsDir => Path.Combine(AppDir, "tools", "platform-tools");

    public static ConfigService Load()
    {
        var cfg = new ConfigService();
        try
        {
            if (File.Exists(ConfigFile))
            {
                var json = File.ReadAllText(ConfigFile);
                var dto = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(json);
                if (dto != null)
                {
                    if (dto.TryGetValue("adb_path", out var a)) cfg.AdbPath = a.GetString() ?? "";
                    if (dto.TryGetValue("serial", out var s)) cfg.Serial = s.GetString() ?? cfg.Serial;
                    if (dto.TryGetValue("geometry", out var g)) cfg.Geometry = g.GetString() ?? cfg.Geometry;
                    if (dto.TryGetValue("microg_uninstall_conflict", out var u)) cfg.MicrogUninstallConflict = u.GetBoolean();
                    if (dto.TryGetValue("microg_grant", out var gr)) cfg.MicrogGrant = gr.GetBoolean();
                    if (dto.TryGetValue("microg_fakegapps", out var f)) cfg.MicrogFakegapps = f.GetBoolean();
                }
            }
        }
        catch
        {
            // 配置损坏就用默认值
        }
        return cfg;
    }

    public void Save()
    {
        try
        {
            var dto = new Dictionary<string, object>
            {
                ["adb_path"] = AdbPath,
                ["serial"] = Serial,
                ["geometry"] = Geometry,
                ["microg_uninstall_conflict"] = MicrogUninstallConflict,
                ["microg_grant"] = MicrogGrant,
                ["microg_fakegapps"] = MicrogFakegapps,
            };
            File.WriteAllText(ConfigFile, JsonSerializer.Serialize(dto, new JsonSerializerOptions { WriteIndented = true }));
        }
        catch
        {
            // 忽略写配置失败
        }
    }
}
