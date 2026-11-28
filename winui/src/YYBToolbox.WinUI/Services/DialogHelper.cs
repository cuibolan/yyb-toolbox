using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace YYBToolbox.WinUI.Services;

public static class DialogHelper
{
    public static async Task<bool> ConfirmAsync(XamlRoot? root, string title, string message)
    {
        var dialog = new ContentDialog
        {
            Title = title,
            Content = message,
            PrimaryButtonText = "确定",
            CloseButtonText = "取消",
            XamlRoot = root,
        };
        var result = await dialog.ShowAsync();
        return result == ContentDialogResult.Primary;
    }

    public static async Task InfoAsync(XamlRoot? root, string title, string message)
    {
        var dialog = new ContentDialog
        {
            Title = title,
            Content = message,
            CloseButtonText = "确定",
            XamlRoot = root,
        };
        await dialog.ShowAsync();
    }
}
