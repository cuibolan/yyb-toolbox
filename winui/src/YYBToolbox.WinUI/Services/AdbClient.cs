using System.Diagnostics;
using System.IO;
using System.Text;
using YYBToolbox.WinUI.Models;

namespace YYBToolbox.WinUI.Services;

public class AdbClient
{
    public const string DefaultSerial = "127.0.0.1:5555";
    private const int CreateNoWindow = 0x08000000;

    public string Exe { get; private set; }
    public string Serial { get; set; }

    public AdbClient(string exe, string serial)
    {
        Exe = exe;
        Serial = string.IsNullOrWhiteSpace(serial) ? DefaultSerial : serial;
    }

    public bool Ready => !string.IsNullOrEmpty(Exe) && File.Exists(Exe);

    // ------------------------------------------------------------ 查找 adb
    public static List<string> Candidates()
    {
        var res = new List<string>();
        var localTools = Path.Combine(ConfigService.AppDirectory, "tools", "platform-tools", "adb.exe");
        if (File.Exists(localTools)) res.Add(localTools);

        var envAdb = Environment.GetEnvironmentVariable("ADB_PATH");
        if (!string.IsNullOrWhiteSpace(envAdb)) res.Add(envAdb.Trim());

        var pathEnv = Environment.GetEnvironmentVariable("PATH") ?? "";
        foreach (var dir in pathEnv.Split(Path.PathSeparator, StringSplitOptions.RemoveEmptyEntries))
        {
            try
            {
                var p = Path.Combine(dir.Trim(), "adb.exe");
                if (File.Exists(p)) res.Add(p);
            }
            catch { }
        }

        var localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        res.AddRange(new[]
        {
            @"D:\Program Files\platform-tools\adb.exe",
            @"C:\Program Files\platform-tools\adb.exe",
            @"C:\platform-tools\adb.exe",
            Path.Combine(localAppData, "Android", "Sdk", "platform-tools", "adb.exe"),
        });

        foreach (var baseDir in new[] { @"C:\Program Files", @"D:\Program Files", @"C:\Program Files (x86)" })
            res.Add(Path.Combine(baseDir, "platform-tools", "adb.exe"));

        foreach (var drive in new[] { "C:", "D:", "E:", "F:" })
        {
            foreach (var sub in new[]
            {
                Path.Combine(drive + @"\Program Files\Tencent\Androws\Application"),
                Path.Combine(drive + @"Program Files (x86)\Tencent\Androws\Application"),
            })
            {
                try
                {
                    if (!Directory.Exists(sub)) continue;
                    foreach (var d in Directory.GetDirectories(sub).OrderByDescending(x => x))
                    {
                        var exe = Path.Combine(d, "adb.exe");
                        if (File.Exists(exe)) res.Add(exe);
                    }
                }
                catch { }
            }
        }

        return res.Where(p => !string.IsNullOrEmpty(p) && File.Exists(p)).Distinct().ToList();
    }

    public static string Autodetect(string configured)
    {
        if (!string.IsNullOrWhiteSpace(configured) && File.Exists(configured)) return configured;
        var cands = Candidates();
        return cands.Count > 0 ? cands[0] : "";
    }

    // ------------------------------------------------------------ 基础执行
    private static readonly HashSet<string> NoSerialCommands = new()
    {
        "connect", "disconnect", "devices", "kill-server", "start-server",
        "version", "help", "reconnect", "wait-for-device", "mdns"
    };

    private List<string> BuildCommand(IEnumerable<string> args, string? serial = null)
    {
        var cmd = new List<string> { Exe };
        var useSerial = serial ?? Serial;
        var first = args.FirstOrDefault();
        if (!string.IsNullOrEmpty(useSerial) && first != null && !NoSerialCommands.Contains(first))
            cmd.AddRange(new[] { "-s", useSerial });
        cmd.AddRange(args);
        return cmd;
    }

    private ProcessStartInfo MakeStartInfo(List<string> cmd, bool redirectBinary)
    {
        return new ProcessStartInfo
        {
            FileName = cmd[0],
            Arguments = ArgumentListToString(cmd.Skip(1)),
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
        };
    }

    private static string ArgumentListToString(IEnumerable<string> args)
    {
        static string Quote(string a) => a.Contains(' ') ? $"\"{a}\"" : a;
        return string.Join(" ", args.Select(Quote));
    }

    public string Run(IEnumerable<string> args, string? serial = null, int timeout = 30)
    {
        if (!Ready) throw new AdbError("未找到 adb.exe，请先设置 ADB 路径");
        var cmd = BuildCommand(args, serial);
        try
        {
            using var p = new Process { StartInfo = MakeStartInfo(cmd, false) };
            p.Start();
            var stdout = p.StandardOutput.ReadToEnd();
            var stderr = p.StandardError.ReadToEnd();
            if (!p.WaitForExit(timeout))
            {
                try { p.Kill(); } catch { }
                throw new AdbError($"adb 命令超时（{timeout}s）：{string.Join(" ", args)}");
            }
            var outText = (stdout ?? "") + (stderr ?? "");
            if (p.ExitCode != 0 && string.IsNullOrWhiteSpace(outText))
                throw new AdbError($"adb 执行失败({p.ExitCode})：{string.Join(" ", args)}");
            return outText.Trim();
        }
        catch (FileNotFoundException e)
        {
            throw new AdbError("adb 可执行文件不存在：" + e.Message);
        }
    }

    public string Shell(string command, bool root = false, int timeout = 60, string? serial = null)
    {
        var cmd = root ? $"su -c '{command.Replace("'", "'\\''")}'" : command;
        return Run(new[] { "shell", cmd }, serial, timeout);
    }

    public byte[] ExecOut(IEnumerable<string> args, int timeout = 60)
    {
        if (!Ready) throw new AdbError("未找到 adb.exe");
        var cmd = BuildCommand(new[] { "exec-out" }.Concat(args));
        using var p = new Process { StartInfo = MakeStartInfo(cmd, true) };
        p.Start();
        var stdout = p.StandardOutput.BaseStream;
        using var ms = new MemoryStream();
        stdout.CopyTo(ms);
        p.StandardError.ReadToEnd();
        if (!p.WaitForExit(timeout)) { try { p.Kill(); } catch { } }
        return ms.ToArray();
    }

    // ------------------------------------------------------------ 设备 / 连接
    public List<Dictionary<string, string>> Devices()
    {
        var outText = Run(new[] { "devices", "-l" }, timeout: 20);
        var rows = new List<Dictionary<string, string>>();
        foreach (var line in outText.Split('\n'))
        {
            var t = line.Trim();
            if (t.Length == 0 || t.StartsWith("List of devices")) continue;
            var parts = t.Split(' ', StringSplitOptions.RemoveEmptyEntries);
            if (parts.Length < 2) continue;
            var info = new Dictionary<string, string> { ["serial"] = parts[0], ["state"] = parts[1] };
            foreach (var kv in parts.Skip(2))
            {
                var idx = kv.IndexOf(':');
                if (idx > 0) info[kv[..idx]] = kv[(idx + 1)..];
            }
            rows.Add(info);
        }
        return rows;
    }

    public string Connect(string? serial = null, int timeout = 20)
    {
        Serial = serial ?? Serial;
        Run(new[] { "start-server" }, timeout: 30);
        return Run(new[] { "connect", Serial }, timeout: timeout);
    }

    public string EnsureConnected(string? serial = null, int retries = 3, double waitSec = 4.0)
    {
        Serial = serial ?? Serial;
        var last = "";
        for (var i = 1; i <= retries; i++)
        {
            try { last = Connect(Serial); }
            catch (Exception e) { last = e.Message; }

            List<Dictionary<string, string>> devs;
            try { devs = Devices(); } catch { devs = new(); }

            foreach (var d in devs)
                if (d.GetValueOrDefault("serial") == Serial && d.GetValueOrDefault("state") == "device")
                    return Serial;
            foreach (var d in devs)
                if (d.GetValueOrDefault("state") == "device" && d.GetValueOrDefault("product") == "caas")
                {
                    Serial = d["serial"];
                    return Serial;
                }

            if (i < retries) Thread.Sleep(TimeSpan.FromSeconds(waitSec));
        }
        throw new AdbError($"连接 {Serial} 失败：{(string.IsNullOrEmpty(last) ? "设备未就绪" : last)}");
    }

    public string State(string? serial = null)
    {
        try { return Run(new[] { "get-state" }, serial ?? Serial, 10).Trim(); }
        catch { return "offline"; }
    }

    // ------------------------------------------------------------ 文件传输
    public string PullFile(string remote, string local, bool rootMode = false, int timeout = 600)
    {
        remote = NormalizeRemote(remote);
        var localPath = Path.GetFullPath(local);
        Directory.CreateDirectory(Path.GetDirectoryName(localPath)!);

        var p = StartCapture(new[] { "pull", remote, localPath }, timeout, out var outBytes);
        var outText = Encoding.UTF8.GetString(outBytes).Trim();
        var ok = p.ExitCode == 0 && File.Exists(localPath) && new FileInfo(localPath).Length > 0;

        if (!ok && rootMode)
        {
            try
            {
                var data = ExecOut(new[] { "shell", "su", "-c", $"cat '{remote.Replace("'", "'\\''")}'" }, timeout);
                if (data.Length > 0)
                {
                    File.WriteAllBytes(localPath, data);
                    ok = File.Exists(localPath) && new FileInfo(localPath).Length > 0;
                    outText = "su cat 兜底拉取成功";
                }
            }
            catch (Exception e)
            {
                outText += $"\n{e.GetType().Name}: {e.Message}";
            }
        }

        if (!ok) throw new AdbError($"拉取失败：{(string.IsNullOrEmpty(outText) ? $"adb 返回码 {p.ExitCode}" : outText)}");
        return localPath;
    }

    public void PushFile(string local, string remote, int timeout = 600)
    {
        remote = NormalizeRemote(remote);
        var p = StartCapture(new[] { "push", local, remote }, timeout, out var outBytes);
        var outText = Encoding.UTF8.GetString(outBytes).Trim();
        if (p.ExitCode != 0) throw new AdbError($"推送失败：{(string.IsNullOrEmpty(outText) ? $"adb 返回码 {p.ExitCode}" : outText)}");
    }

    private Process StartCapture(IEnumerable<string> args, int timeout, out byte[] output)
    {
        var cmd = BuildCommand(args);
        var psi = new ProcessStartInfo
        {
            FileName = cmd[0],
            Arguments = ArgumentListToString(cmd.Skip(1)),
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
        };
        var p = Process.Start(psi)!;
        var ms = new MemoryStream();
        p.StandardOutput.BaseStream.CopyTo(ms);
        var err = p.StandardError.ReadToEnd();
        var errBytes = Encoding.UTF8.GetBytes(err ?? "");
        ms.Write(errBytes, 0, errBytes.Length);
        if (!p.WaitForExit(timeout)) { try { p.Kill(); } catch { } }
        output = ms.ToArray();
        return p;
    }

    // ------------------------------------------------------------ 应用管理
    public List<AppInfo> ListPackages(string scope)
    {
        var flags = scope switch { "系统" => "-s", "全部" => "", _ => "-3" };
        var outText = Shell($"pm list packages --show-versioncode {flags}", timeout: 60);
        var disabled = new HashSet<string>();
        try
        {
            var dOut = Shell($"pm list packages -d {flags}", timeout: 60);
            foreach (var line in dOut.Split('\n'))
                if (line.StartsWith("package:"))
                    disabled.Add(line.Split(':', 2)[1].Trim());
        }
        catch { }

        var list = new List<AppInfo>();
        foreach (var line in outText.Split('\n'))
        {
            var t = line.Trim();
            var idx = t.IndexOf("package:");
            if (idx < 0) continue;
            t = t.Substring(idx + 8);
            var ver = "";
            var sp = t.Split(" ", StringSplitOptions.RemoveEmptyEntries);
            var pkg = sp[0].Trim();
            foreach (var part in sp.Skip(1))
                if (part.StartsWith("versionCode:")) ver = part["versionCode:".Length..];
            var type = IsProbablySystem(pkg) ? "系统" : "第三方";
            list.Add(new AppInfo
            {
                Package = pkg,
                VersionCode = ver,
                Type = scope == "第三方" ? "第三方" : scope == "系统" ? "系统" : type,
                State = disabled.Contains(pkg) ? "已禁用" : "已启用",
            });
        }
        return list.OrderBy(a => a.Package).ToList();
    }

    private static bool IsProbablySystem(string pkg) =>
        pkg.StartsWith("com.android.") || pkg.StartsWith("android.") ||
        pkg.StartsWith("com.google.android.") || pkg.StartsWith("com.qualcomm.");

    public void StartPackage(string pkg, string? activity = null)
    {
        var comp = string.IsNullOrEmpty(activity) ? "" : $"{pkg}/{activity}";
        if (comp == "")
        {
            var resolve = Shell($"cmd package resolve-activity --brief {ShellQuote(pkg)}", timeout: 30);
            foreach (var line in resolve.Split('\n'))
            {
                var l = line.Trim();
                if (l.Contains('/') && !l.Contains("No activity")) { comp = l; break; }
            }
        }

        var attempts = new List<string>();
        if (!string.IsNullOrEmpty(comp)) attempts.Add($"am start -n {comp}");
        attempts.Add($"monkey -p {ShellQuote(pkg)} -c android.intent.category.LAUNCHER 1");

        var last = "";
        foreach (var cmd in attempts)
        {
            var res = Shell(cmd, timeout: 40);
            last = res;
            if (res.Contains("Error") || res.Contains("Exception") || res.Contains("No activities found"))
                continue;
            return;
        }
        var tail = last.Trim();
        if (tail.Length > 300) tail = tail[..300];
        throw new AdbError($"应用没有在引擎里显示出来。常见原因：启动即闪退或窗口被挡住。命令输出：{tail}");
    }

    public void ForceStop(string pkg) => Run(new[] { "shell", "am", "force-stop", pkg }, timeout: 30);
    public void ClearData(string pkg) => Run(new[] { "shell", "pm", "clear", pkg }, timeout: 60);
    public void Uninstall(string pkg) => Run(new[] { "uninstall", pkg }, timeout: 60);
    public void Enable(string pkg) => Run(new[] { "shell", "pm", "enable", pkg }, timeout: 30);
    public void Disable(string pkg) => Run(new[] { "shell", "pm", "disable-user", pkg }, timeout: 30);

    public string PackagePath(string pkg)
    {
        var outText = Run(new[] { "shell", "pm", "path", pkg }, timeout: 30);
        foreach (var line in outText.Split('\n'))
            if (line.StartsWith("package:")) return line.Split(':', 2)[1].Trim();
        return "";
    }

    public void InstallApk(string apk) => Run(new[] { "install", "-r", apk }, timeout: 300);

    // ------------------------------------------------------------ 截图 / 日志
    public byte[] Screenshot()
    {
        var data = ExecOut(new[] { "screencap", "-p" }, timeout: 60);
        if (data.Length < 8 || data[0] != 0x89 || data[1] != 0x50 || data[2] != 0x4E || data[3] != 0x47)
            throw new AdbError("截图失败：返回数据不是 PNG（可重连引擎后再试）");
        return data;
    }

    public Process StartLogcat(string? filterTag, string? level)
    {
        var args = new List<string> { "logcat" };
        if (!string.IsNullOrEmpty(level)) args.Add(level + ":*");
        if (!string.IsNullOrWhiteSpace(filterTag)) args.AddRange(new[] { "-s", $"{filterTag}:V" });
        args.Add("-v"); args.Add("time");
        var cmd = BuildCommand(args);
        var psi = new ProcessStartInfo
        {
            FileName = cmd[0],
            Arguments = ArgumentListToString(cmd.Skip(1)),
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
        };
        var p = Process.Start(psi)!;
        // 丢弃 stderr，避免错误输出填满管道导致进程堵死
        p.ErrorDataReceived += (_, e) => { };
        p.BeginErrorReadLine();
        return p;
    }

    // ------------------------------------------------------------ 文件浏览
    private static string ShellQuote(string a) => "'" + a.Replace("'", "'\\''") + "'";

    /// <summary>判断远程路径（含软链接）是否指向目录。</summary>
    public bool IsRemoteDir(string remote, bool rootMode = false, int timeout = 30)
    {
        remote = NormalizeRemote(remote);
        var outText = Shell($"[ -d {ShellQuote(remote)} ] && echo DIR || echo FILE", root: rootMode, timeout: timeout);
        return outText.Contains("DIR");
    }

    /// <summary>解析软链接链，返回真实路径（readlink -f）。</summary>
    public string RealPath(string remote, bool rootMode = false, int timeout = 30)
    {
        remote = NormalizeRemote(remote);
        var outText = Shell($"readlink -f {ShellQuote(remote)}", root: rootMode, timeout: timeout).Trim();
        return string.IsNullOrWhiteSpace(outText) ? remote : NormalizeRemote(outText);
    }

    public List<FileEntry> ListDir(string path, bool rootMode = false)
    {
        var real = RealPath(path, rootMode);
        var raw = Shell($"ls -la {ShellQuote(real)}", root: rootMode, timeout: 30);
        var low = raw.ToLowerInvariant();
        if (low.Contains("permission denied"))
            throw new AdbError("没有权限读取这个目录（系统目录需要 Root），请勾选「Root 浏览」后再试");
        if (low.Contains("no such file or directory"))
            throw new AdbError($"路径不存在：{path}");
        if (low.Contains("not a directory"))
            throw new AdbError("这不是目录，而是文件");

        var list = new List<FileEntry>();
        foreach (var line in raw.Split('\n'))
        {
            var t = line.TrimEnd();
            if (string.IsNullOrWhiteSpace(t) || t.StartsWith("total")) continue;

            var parts = t.Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries);
            if (parts.Length < 8) continue;

            var perm = parts[0];
            var size = parts[4];
            var mtime = $"{parts[5]} {parts[6]}";
            var namePart = string.Join(" ", parts.Skip(7)).Trim();

            var name = namePart;
            var target = "";
            var arrow = namePart.IndexOf(" -> ");
            if (arrow >= 0)
            {
                target = namePart.Substring(arrow + 4);
                name = namePart.Substring(0, arrow);
            }
            if (name is "." or "..") continue;

            var kind = perm[0];
            bool isDir = kind == 'd';
            list.Add(new FileEntry
            {
                Name = name,
                IsDir = isDir,
                Type = kind == 'l' ? "链接" : isDir ? "目录" : "文件",
                Size = size,
                Perm = perm,
                Mtime = mtime,
                Target = target,
            });
        }
        return list.OrderByDescending(f => f.IsDir).ThenBy(f => f.Name, StringComparer.OrdinalIgnoreCase).ToList();
    }

    public void RemovePath(string remote, bool recursive, bool rootMode = false)
    {
        Shell(recursive ? $"rm -rf {ShellQuote(remote)}" : $"rm -f {ShellQuote(remote)}", root: rootMode, timeout: 60);
    }

    public string JoinRemote(string parent, string name) =>
        NormalizeRemote(parent.TrimEnd('/') + "/" + name);

    /// <summary>规范化安卓端路径：反斜杠转正斜杠、补前导 /、合并重复斜杠、去尾部 /。</summary>
    public static string NormalizeRemote(string? path)
    {
        var p = (path ?? "").Replace('\\', '/').Trim();
        if (p.Length == 0) return "/";
        if (!p.StartsWith('/')) p = "/" + p;
        while (p.Contains("//")) p = p.Replace("//", "/");
        p = p.TrimEnd('/');
        return p.Length == 0 ? "/" : p;
    }

    /// <summary>取远程路径的父目录，不依赖 Windows 路径规则。</summary>
    public static string RemoteParent(string path)
    {
        var p = NormalizeRemote(path);
        if (p == "/") return "/";
        var idx = p.LastIndexOf('/');
        return idx <= 0 ? "/" : p.Substring(0, idx);
    }

    /// <summary>清洗本地文件名里的 Windows 非法字符。</summary>
    public static string SanitizeWindowsName(string name)
    {
        var invalid = Path.GetInvalidFileNameChars();
        var sb = new StringBuilder();
        foreach (var c in name) sb.Append(invalid.Contains(c) ? '_' : c);
        var cleaned = sb.ToString().Trim();
        return cleaned.Length == 0 ? "unnamed" : cleaned;
    }
}
