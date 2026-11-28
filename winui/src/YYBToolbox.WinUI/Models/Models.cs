namespace YYBToolbox.WinUI.Models;

public class AppInfo
{
    public string Package { get; set; } = "";
    public string VersionCode { get; set; } = "";
    public string Type { get; set; } = "";
    public string State { get; set; } = "";
}

public class FileEntry
{
    public string Name { get; set; } = "";
    public bool IsDir { get; set; }
    public string Type { get; set; } = "";
    public string Size { get; set; } = "";
    public string Perm { get; set; } = "";
    public string Mtime { get; set; } = "";
    public string Target { get; set; } = "";
}

public class DeviceInfo
{
    public string Model { get; set; } = "?";
    public string Brand { get; set; } = "?";
    public string Android { get; set; } = "?";
    public string Sdk { get; set; } = "?";
    public string Abi { get; set; } = "?";
    public string Resolution { get; set; } = "?";
    public string Density { get; set; } = "?";
    public string Storage { get; set; } = "?";
    public string Memory { get; set; } = "?";
    public string Battery { get; set; } = "?";
    public string Uptime { get; set; } = "?";
    public string Selinux { get; set; } = "?";
    public bool Root { get; set; }
    public string Magisk { get; set; } = "";
    public string Serial { get; set; } = "";
}
