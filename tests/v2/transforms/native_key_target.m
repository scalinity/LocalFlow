// Disposable synthetic target for actual session event-tap qualification.
// It never launches a command, opens a document, or sends a message.
#import <Cocoa/Cocoa.h>
#include <unistd.h>

static NSString *statePath, *commandPath;
static NSUInteger returns = 0, writes = 0, menuActions = 0;
static NSMutableSet *operations;
static NSTextView *field;
static NSTextView *otherField;

@interface LFKeyTargetField : NSTextView @end
@implementation LFKeyTargetField
- (void)keyDown:(NSEvent *)event {
    if (event.keyCode == 36 || event.keyCode == 76) returns++;
    [super keyDown:event];
}
@end

@interface LFKeyTarget : NSObject <NSApplicationDelegate>
@property NSWindow *window;
@end
@implementation LFKeyTarget
- (void)menuTest:(id)sender { menuActions++; }
- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    operations = [NSMutableSet set];
    self.window = [[NSWindow alloc] initWithContentRect:NSMakeRect(160,160,480,200)
        styleMask:NSWindowStyleMaskTitled|NSWindowStyleMaskClosable
        backing:NSBackingStoreBuffered defer:NO];
    self.window.title = @"LocalFlow synthetic keyboard qualification";
    field = [[LFKeyTargetField alloc] initWithFrame:NSMakeRect(0,0,480,200)];
    field.string = @"This is a test prompt";
    NSView *container = [[NSView alloc] initWithFrame:NSMakeRect(0,0,480,200)];
    self.window.contentView = container;
    [container addSubview:field];
    [self.window makeKeyAndOrderFront:nil];
    [self.window makeFirstResponder:field];
    NSMenu *bar = [NSMenu new];
    NSMenuItem *application = [NSMenuItem new];
    application.submenu = [[NSMenu alloc] initWithTitle:@"Application"];
    [bar addItem:application];
    NSMenuItem *top = [[NSMenuItem alloc] initWithTitle:@"Qualification" action:nil keyEquivalent:@""];
    NSMenu *menu = [[NSMenu alloc] initWithTitle:@"Qualification"];
    NSMenuItem *item = [[NSMenuItem alloc] initWithTitle:@"Count menu acceptance" action:@selector(menuTest:) keyEquivalent:@""];
    item.target = self;
    [menu addItem:item]; top.submenu = menu; [bar addItem:top]; NSApp.mainMenu = bar;
    [NSApp activateIgnoringOtherApps:YES];
    [NSTimer scheduledTimerWithTimeInterval:0.02 target:self selector:@selector(tick:) userInfo:nil repeats:YES];
    [self tick:nil];
}
- (void)tick:(NSTimer *)timer {
    NSData *data = [NSData dataWithContentsOfFile:commandPath];
    NSDictionary *command = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
    NSString *operation = command[@"operation"];
    if (operation && ![operations containsObject:operation]) {
        [operations addObject:operation];
        if ([command[@"action"] isEqual:@"quit"]) { [NSApp terminate:nil]; return; }
        if ([command[@"action"] isEqual:@"replace"] && [command[@"text"] isKindOfClass:NSString.class]) {
            field.string = command[@"text"]; writes++;
        }
        if ([command[@"action"] isEqual:@"focus-other"]) {
            if (!otherField) {
                field.frame = NSMakeRect(0,60,480,140);
                otherField = [[LFKeyTargetField alloc] initWithFrame:NSMakeRect(0,0,480,60)];
                [self.window.contentView addSubview:otherField];
            }
            [self.window makeFirstResponder:otherField];
        }
        if ([command[@"action"] isEqual:@"focus-original"]) [self.window makeFirstResponder:field];
    }
    NSDictionary *state = @{@"pid":@(getpid()), @"return_events":@(returns),
        @"writes":@(writes), @"text":field.string, @"active":@(NSApp.active),
        @"menu_actions":@(menuActions), @"other_text":otherField ? otherField.string : @"",
        @"original_focused":@(self.window.firstResponder == field)};
    [[NSJSONSerialization dataWithJSONObject:state options:0 error:nil]
        writeToFile:statePath atomically:YES];
}
@end

int main(int argc, const char **argv) {
    @autoreleasepool {
        if (argc != 3) return 2;
        statePath = [NSString stringWithUTF8String:argv[1]];
        commandPath = [NSString stringWithUTF8String:argv[2]];
        NSApplication *app = NSApplication.sharedApplication;
        [app setActivationPolicy:NSApplicationActivationPolicyRegular];
        LFKeyTarget *delegate = [LFKeyTarget new]; app.delegate = delegate;
        [app run];
    }
    return 0;
}
