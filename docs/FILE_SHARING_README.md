# Group File Sharing Feature

## Overview
The file sharing feature allows group members to upload, share, and manage documents within their CRM groups. This includes proposal templates, contracts, presentations, and other business documents.

## Features

### 📁 File Categories
- **Proposal Templates** - Sales proposal templates and examples
- **Contracts** - Contract templates and signed agreements
- **Presentations** - PowerPoint presentations and pitch decks
- **Forms & Documents** - Various business forms and documents
- **Resources & Guidelines** - Reference materials and company guidelines
- **Training Materials** - Training documents and resources
- **Other Documents** - Miscellaneous files

### 🔐 Access Control
- **Group-based Access**: Users can only access files from groups they belong to
- **Role-based Permissions**:
  - **Executives** (Admin, President, GM, VP): Access all group files
  - **AVP**: Access files from their managed teams
  - **ASM**: Access files from their assigned teams  
  - **Supervisors**: Access files from their managed groups
  - **Team Leads**: Access files from their led groups
  - **Sales Agents**: Access files from their own group

### 📤 File Upload
- **Supported Formats**: PDF, Word, Excel, PowerPoint, Text, Images (JPG, PNG, GIF), Archives (ZIP, RAR)
- **File Size Limit**: 50MB per file
- **Validation**: Automatic file type and size validation
- **Metadata**: Automatic file size and MIME type detection

### 📊 File Management
- **File Details**: View comprehensive file information and download history
- **Edit Metadata**: Update file title, description, category, and active status
- **Delete Files**: Authorized users can delete files with audit logging
- **Search & Filter**: Search by title/description and filter by category
- **Download Tracking**: Track download counts and access logs

### 🔍 Navigation & Views
- **All Group Files**: View files from all accessible groups
- **My Uploaded Files**: View and manage your uploaded files
- **Group-specific Files**: View files for a specific group
- **File Details**: Detailed view with access history

## URLs
- `/files/all-files/` - View all accessible group files
- `/files/my-files/` - View your uploaded files
- `/files/group/<group_id>/files/` - View files for specific group
- `/files/group/<group_id>/upload/` - Upload file to group
- `/files/file/<file_id>/` - View file details
- `/files/file/<file_id>/download/` - Download file
- `/files/file/<file_id>/edit/` - Edit file metadata
- `/files/file/<file_id>/delete/` - Delete file

## Database Models

### GroupFileShare
Main model for storing shared files:
- Group association
- File upload with validation
- Metadata (title, description, category)
- Upload tracking (user, timestamp)
- Access control (active status)
- Download statistics

### FileCategory
Predefined categories for organizing files:
- Category name and description
- Display icons

### FileAccessLog
Audit trail for file access:
- User actions (upload, download, view, delete)
- Timestamps and IP addresses
- User agent tracking

## Security Features
- **File Validation**: Only allowed file types accepted
- **Size Limits**: 50MB maximum file size
- **Access Control**: Group-based file access
- **Audit Logging**: Complete access history
- **Secure Downloads**: Proper file serving with security headers

## Integration
The file sharing feature integrates seamlessly with the existing CRM:
- **Navigation**: Added to main navbar under "Files" dropdown
- **Group Pages**: "Group Files" button added to group member pages
- **Permissions**: Respects existing role hierarchy and group membership
- **UI/UX**: Consistent with existing Bootstrap 5 styling

## Usage Instructions

### For Group Members:
1. Navigate to your group via Teams > All Groups
2. Click "Group Files" button on the group members page
3. Click "Upload File" to share a new document
4. Use search and filters to find specific files
5. Click file titles to view details and download history

### For Administrators:
- Access Django admin to manage files and view access logs
- Monitor file usage through the FileAccessLog model
- Manage file categories and organize shared content

## File Storage
- Files are stored in `media/group_files/<group_id>/<category>/`
- Organized by group and category for easy management
- Automatic cleanup when files are deleted through the interface

## Next Steps for Production
1. Configure secure file serving (nginx)
2. Set up proper backup strategy for uploaded files
3. Consider cloud storage integration (AWS S3, etc.)
4. Implement file versioning if needed
5. Add virus scanning for uploaded files
6. Set up proper SSL/HTTPS configuration
