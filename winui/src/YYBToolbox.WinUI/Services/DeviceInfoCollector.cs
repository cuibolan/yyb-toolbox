using System.Text.RegularExpressions;
using YYBToolbox.WinUI.Models;

namespace YYBToolbox.WinUI.Services;

public static class DeviceInfoCollector
{
    public static DeviceInfo Collect(AdbClient adb)
    {
        var info = new DeviceInfo { Serial = adb.Serial };

        Dictionary<string, string> props;
        try
        {
            props = ParseGetprop(adb.Shell("getprop", timeout: 30));
        }
        catch { props = new(); }

        info.Model = props.GetValueOrDefault("ro.product.model", "?");
        info.Brand = props.GetValueOrDefault("ro.product.brand", "?");
        info.Android = props.GetValueOrDefault("ro.build.version.release", "?");
        info.Sdk = props.GetValueOrDefault("ro.build.version.sdk", "?");
        info.Abi = props.GetValueOrDefault("ro.product.cpu.abi", "?");

        try
        {
            var wm = adb.Shell("wm size", timeout: 20);
            var size = PickAfter(wm, "Override size") ?? PickAfter(wm, "Physical size") ?? "?";
            info.Resolution = size;

            var dens = adb.Shell("wm density", timeout: 20);
            info.Density = PickAfter(dens, "Override density") ?? PickAfter(dens, "Physical density") ?? "?";
        }
        catch { info.Resolution = info.Density = "?"; }

        try
        {
            var df = adb.Shell("df -h /data /storage/emulated 2>/dev/null", timeout: 30);
            string[]? target = null;
            foreach (var line in df.Split('\n').Skip(1))
            {
                var parts = line.Split(' ', StringSplitOptions.RemoveEmptyEntries);
                if (parts.Length >= 6 && parts[^1].Contains("/data")) target = parts;
            }
            if (target == null)
                foreach (var line in df.Split('\n').Skip(1))
                {
                    var parts = line.Split(' ', StringSplitOptions.RemoveEmptyEntries);
                    if (parts.Length >= 6 && parts[^1].Contains("emulated")) target = parts;
                }
            info.Storage = target != null ? $"{target[2]} / {target[1]}（剩余 {target[3]}）" : "?";
        }
        catch { info.Storage = "?"; }

        try
        {
            var mem = adb.Shell("cat /proc/meminfo", timeout: 20);
            long total = 0, avail = 0;
            foreach (var line in mem.Split('\n'))
            {
                if (line.StartsWith("MemTotal:")) total = long.Parse(line.Split()[1]) * 1024;
                else if (line.StartsWith("MemAvailable:")) avail = long.Parse(line.Split()[1]) * 1024;
            }
            info.Memory = total > 0 ? $"{FmtSize(total - avail)} / {FmtSize(total)} 已用" : "?";
        }
        catch { info.Memory = "?"; }

        try
        {
            var bat = adb.Shell("dumpsys battery", timeout: 20);
            string level = "?", temp = "?";
            foreach (var line in bat.Split('\n'))
            {
                var t = line.Trim();
                if (t.StartsWith("level:")) level = t.Split(':', 2)[1].Trim();
                else if (t.StartsWith("temperature:")) temp = t.Split(':', 2)[1].Trim();
            }
            info.Battery = long.TryParse(temp, out var tNum) ? $"{level}% / {tNum / 10.0:F1}℃" : $"{level}%";
        }
        catch { info.Battery = "?"; }

        try
        {
            var up = double.Parse(adb.Shell("cat /proc/uptime", timeout: 10).Split()[0]);
            info.Uptime = $"{(int)(up / 3600)} 小时 {(int)(up % 3600 / 60)} 分";
        }
        catch { info.Uptime = "?"; }

        try { info.Selinux = adb.Shell("getenforce", timeout: 10).Trim() is { Length: > 0 } s ? s : "?"; }
        catch { info.Selinux = "?"; }

        try
        {
            var id = adb.Shell("id", root: true, timeout: 20);
            if (id.Contains("uid=0"))
            {
                info.Root = true;
                info.Magisk = adb.Shell("magisk -v", root: true, timeout: 20).Trim();
            }
        }
        catch { }

        return info;
    }

    private static Dictionary<string, string> ParseGetprop(string text)
    {
        var dict = new Dictionary<string, string>();
        foreach (var line in text.Split('\n'))
        {
            var m = Regex.Match(line.Trim(), @"^\[([^\]]+)\]: \[(.*)\]$");
            if (m.Success) dict[m.Groups[1].Value] = m.Groups[2].Value;
        }
        return dict;
    }

    private static string? PickAfter(string text, string label)
    {
        foreach (var line in text.Split('\n'))
            if (line.Contains(label)) return line.Split(':', 2)[1].Trim();
        return null;
    }

    public static string FmtSize(long bytes)
    {
        var v = (double)bytes;
        foreach (var unit in new[] { "B", "KB", "MB", "GB", "TB" })
        {
            if (v < 1024 || unit == "TB") return unit == "B" ? $"{(int)v} B" : $"{v:F1} {unit}";
            v /= 1024;
        }
        return $"{v:F1} TB";
    }
}
